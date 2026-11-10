//! Single files out of a remote ZIP, via HTTP range requests: the index once, then only the
//! bytes of each file asked for.

use std::io::Read;
use std::time::Duration;

use reqwest::header::{CONTENT_RANGE, RANGE};
use reqwest::{Client, StatusCode};
use serde::{Deserialize, Serialize};

use crate::{Error, Result};

const TIMEOUT: Duration = Duration::from_secs(30);
/// The end-of-central-directory record (22 bytes) plus the longest possible archive comment.
const TAIL: u64 = 22 + u16::MAX as u64;

/// One file in the archive's central directory.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct Entry {
    pub name: String,
    offset: u64,
    compressed: u64,
    method: u16,
}

/// Every entry in the ZIP at `url`, from its central directory.
pub(crate) async fn index(client: &Client, url: &str) -> Result<Vec<Entry>> {
    let tail = range(client, url, &format!("bytes=-{TAIL}")).await?;
    let (offset, size) = end_of_directory(&tail)?;
    let directory = range(
        client,
        url,
        &format!("bytes={offset}-{}", offset + size - 1),
    )
    .await?;
    central_directory(&directory)
}

/// The uncompressed contents of `entry`.
pub(crate) async fn fetch(client: &Client, url: &str, entry: &Entry) -> Result<Vec<u8>> {
    // The local header's name and extra lengths can differ from the central directory's.
    let header = range(
        client,
        url,
        &format!("bytes={}-{}", entry.offset, entry.offset + 29),
    )
    .await?;
    let start = entry.offset + 30 + u64::from(le16(&header, 26)?) + u64::from(le16(&header, 28)?);
    let data = if entry.compressed == 0 {
        Vec::new()
    } else {
        range(
            client,
            url,
            &format!("bytes={start}-{}", start + entry.compressed - 1),
        )
        .await?
    };
    match entry.method {
        0 => Ok(data),
        8 => {
            let mut out = Vec::new();
            flate2::read::DeflateDecoder::new(data.as_slice()).read_to_end(&mut out)?;
            Ok(out)
        }
        method => Err(zip_error(format!(
            "{}: unsupported compression method {method}",
            entry.name
        ))),
    }
}

/// A byte range; a server that ignores `Range` would send the whole archive, so that's an error.
async fn range(client: &Client, url: &str, range: &str) -> Result<Vec<u8>> {
    let response = client
        .get(url)
        .header(RANGE, range)
        .timeout(TIMEOUT)
        .send()
        .await?
        .error_for_status()?;
    if response.status() != StatusCode::PARTIAL_CONTENT
        || !response.headers().contains_key(CONTENT_RANGE)
    {
        return Err(zip_error(format!("{url} does not support range requests")));
    }
    Ok(response.bytes().await?.to_vec())
}

/// Offset and size of the central directory, from the archive's last bytes.
fn end_of_directory(tail: &[u8]) -> Result<(u64, u64)> {
    let at = tail
        .windows(4)
        .rposition(|w| w == [0x50, 0x4b, 0x05, 0x06])
        .ok_or_else(|| zip_error("no end of central directory".into()))?;
    let (entries, size, offset) = (
        le16(tail, at + 10)?,
        le32(tail, at + 12)?,
        le32(tail, at + 16)?,
    );
    // shortcut: no ZIP64, so archives must stay under 4 GB and 65,535 entries; add the ZIP64 locator if a pack outgrows that.
    if entries == u16::MAX || offset == u32::MAX {
        return Err(zip_error("ZIP64 archives are not supported".into()));
    }
    Ok((u64::from(offset), u64::from(size)))
}

fn central_directory(bytes: &[u8]) -> Result<Vec<Entry>> {
    let mut entries = Vec::new();
    let mut at = 0;
    while bytes.get(at..at + 4) == Some(&[0x50, 0x4b, 0x01, 0x02]) {
        let name_len = usize::from(le16(bytes, at + 28)?);
        let skip =
            name_len + usize::from(le16(bytes, at + 30)?) + usize::from(le16(bytes, at + 32)?);
        let name = bytes
            .get(at + 46..at + 46 + name_len)
            .ok_or_else(|| zip_error("truncated entry name".into()))?;
        entries.push(Entry {
            name: String::from_utf8_lossy(name).into_owned(),
            method: le16(bytes, at + 10)?,
            compressed: u64::from(le32(bytes, at + 20)?),
            offset: u64::from(le32(bytes, at + 42)?),
        });
        at += 46 + skip;
    }
    Ok(entries)
}

fn le16(bytes: &[u8], at: usize) -> Result<u16> {
    let raw = bytes
        .get(at..at + 2)
        .ok_or_else(|| zip_error("truncated header".into()))?;
    Ok(u16::from_le_bytes([raw[0], raw[1]]))
}

fn le32(bytes: &[u8], at: usize) -> Result<u32> {
    let raw = bytes
        .get(at..at + 4)
        .ok_or_else(|| zip_error("truncated header".into()))?;
    Ok(u32::from_le_bytes([raw[0], raw[1], raw[2], raw[3]]))
}

fn zip_error(message: String) -> Error {
    Error::Config(format!("icon pack: {message}"))
}

#[cfg(test)]
pub(crate) mod tests {
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};

    use super::*;

    /// An archive with a deflated and a stored icon, plus macOS's resource-fork noise.
    pub(crate) fn archive() -> Vec<u8> {
        let mut zip = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
        let deflated = zip::write::SimpleFileOptions::default();
        let stored = deflated.compression_method(zip::CompressionMethod::Stored);
        for (name, options, body) in [
            (
                "__MACOSX/Pack/64/._Arch_Amazon-RDS_64.png",
                deflated,
                b"fork".as_slice(),
            ),
            (
                "Pack/Databases/64/Arch_Amazon-RDS_64.png",
                deflated,
                b"rds rds rds rds rds".as_slice(),
            ),
            ("bigquery/bigquery.png", stored, b"bigquery".as_slice()),
        ] {
            zip.start_file(name, options).unwrap();
            zip.write_all(body).unwrap();
        }
        zip.finish().unwrap().into_inner()
    }

    /// Serves `body` honouring `Range`, recording every range asked for.
    pub(crate) fn range_server(body: Vec<u8>) -> (String, Arc<Mutex<Vec<String>>>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/pack.zip", listener.local_addr().unwrap());
        let ranges = Arc::new(Mutex::new(Vec::new()));
        let seen = ranges.clone();
        std::thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let mut reader = BufReader::new(stream);
                let mut head = String::new();
                while reader.read_line(&mut head).unwrap_or(0) > 2 {}
                let spec = head
                    .lines()
                    .find_map(|l| {
                        l.to_lowercase()
                            .strip_prefix("range: bytes=")
                            .map(str::to_owned)
                    })
                    .unwrap_or_default();
                seen.lock().unwrap().push(spec.clone());
                let len = body.len();
                let (start, end) = match spec.split_once('-') {
                    Some(("", n)) => (len.saturating_sub(n.parse().unwrap()), len - 1),
                    Some((a, b)) => (a.parse().unwrap(), b.parse::<usize>().unwrap().min(len - 1)),
                    None => (0, len - 1),
                };
                let mut stream = reader.into_inner();
                let _ = write!(
                    stream,
                    "HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {start}-{end}/{len}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    end - start + 1
                );
                let _ = stream.write_all(&body[start..=end]);
            }
        });
        (url, ranges)
    }

    #[tokio::test]
    async fn reads_the_index_then_only_the_requested_file() {
        let body = archive();
        let total = body.len();
        let (url, ranges) = range_server(body);
        let client = Client::new();
        let entries = index(&client, &url).await.unwrap();
        assert_eq!(entries.len(), 3);
        let rds = entries
            .iter()
            .find(|e| e.name.ends_with("Arch_Amazon-RDS_64.png") && !e.name.starts_with("__"))
            .unwrap();
        assert_eq!(
            fetch(&client, &url, rds).await.unwrap(),
            b"rds rds rds rds rds"
        );
        let bigquery = entries
            .iter()
            .find(|e| e.name == "bigquery/bigquery.png")
            .unwrap();
        assert_eq!(fetch(&client, &url, bigquery).await.unwrap(), b"bigquery");
        let ranges = ranges.lock().unwrap();
        assert!(
            !ranges
                .iter()
                .any(|r| r.is_empty() || *r == format!("0-{}", total - 1)),
            "never the whole archive: {ranges:?}"
        );
    }
}
