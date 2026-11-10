//! Icons read one at a time out of remote ZIP archives.

use std::path::PathBuf;

use glob::{MatchOptions, Pattern};
use serde::Deserialize;
use tokio::fs;
use tokio::sync::OnceCell;

use super::zip::{self, Entry};
use super::{Icons, find_case_insensitive};
use crate::cache::atomic_write;

/// A remote ZIP of icons, read lazily: [`IconSource::Pack`] fetches the archive's index once,
/// then only the bytes of each icon used. The host must support HTTP range requests.
///
/// ```toml
/// [icon_packs.gcp]
/// url = "https://services.google.com/fh/files/misc/google-cloud-legacy-icons.zip"
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IconPack {
    pub url: String,
}

pub(super) struct Pack {
    url: String,
    index: OnceCell<Option<Vec<Entry>>>,
}

impl std::fmt::Debug for Pack {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.url)
    }
}

impl Icons {
    /// Icon packs [`IconSource::Pack`] can name.
    #[must_use]
    pub fn with_packs(mut self, packs: impl IntoIterator<Item = (String, IconPack)>) -> Self {
        self.packs.extend(packs.into_iter().map(|(name, pack)| {
            (
                name,
                Pack {
                    url: pack.url,
                    index: OnceCell::new(),
                },
            )
        }));
        self
    }

    /// `<pack>/<file glob>`: a cached copy, else the first matching archive entry, fetched alone.
    pub(super) async fn pack_icon(&self, spec: &str) -> Option<PathBuf> {
        let (name, file) = spec.split_once('/')?;
        let dir = self.dir.join("packs").join(name);
        if let Some(cached) = find_case_insensitive(&dir, file).await {
            return Some(cached);
        }
        let pack = self.packs.get(name).or_else(|| {
            log::warn!("icon pack {name:?} is not configured");
            None
        })?;
        let entries = pack
            .index
            .get_or_init(|| self.pack_index(name, &pack.url))
            .await
            .as_ref()?;
        let pattern = Pattern::new(file).ok()?;
        let options = MatchOptions {
            case_sensitive: false,
            ..MatchOptions::new()
        };
        // macOS-made archives carry resource forks under __MACOSX/.
        let entry = entries
            .iter()
            .filter(|e| !e.name.starts_with("__MACOSX/"))
            .find(|e| {
                let base = e.name.rsplit('/').next().unwrap_or(&e.name);
                pattern.matches_with(base, options)
            })?;
        let bytes = zip::fetch(&self.client, &pack.url, entry)
            .await
            .map_err(|e| log::warn!("icon pack {name}: {e}"))
            .ok()?;
        let path = dir.join(entry.name.rsplit('/').next()?);
        atomic_write(&path, &bytes).await.ok()?;
        Some(path)
    }

    /// The pack's index from disk when it's for the same URL, else from the archive.
    async fn pack_index(&self, name: &str, url: &str) -> Option<Vec<Entry>> {
        #[derive(serde::Serialize, Deserialize)]
        struct Cached {
            url: String,
            entries: Vec<Entry>,
        }
        let path = self.dir.join("packs").join(format!("{name}.index.json"));
        if let Ok(raw) = fs::read(&path).await
            && let Ok(cached) = serde_json::from_slice::<Cached>(&raw)
            && cached.url == url
        {
            return Some(cached.entries);
        }
        let entries = zip::index(&self.client, url)
            .await
            .map_err(|e| log::warn!("icon pack {name}: {e}"))
            .ok()?;
        let cached = Cached {
            url: url.to_owned(),
            entries,
        };
        if let Ok(json) = serde_json::to_vec(&cached) {
            let _ = atomic_write(&path, &json).await;
        }
        Some(cached.entries)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::IconSource;

    #[tokio::test]
    pub(super) async fn pack_icons_fetch_one_entry_and_cache_it() {
        let (url, ranges) =
            super::super::zip::tests::range_server(super::super::zip::tests::archive());
        let dir = tempfile::tempdir().unwrap();
        let icons = Icons::new(dir.path()).with_packs([("aws".to_owned(), IconPack { url })]);
        let source = IconSource::Pack("aws/arch_amazon-rds_64.png".into());
        let icon = icons.resolve(&source).await.unwrap();
        assert!(
            icon.path.ends_with("packs/aws/Arch_Amazon-RDS_64.png"),
            "{}",
            icon.path
        );
        assert_eq!(std::fs::read(&icon.path).unwrap(), b"rds rds rds rds rds");
        let requests = ranges.lock().unwrap().len();
        assert_eq!(
            icons.resolve(&source).await,
            Some(icon),
            "served from the cache"
        );
        assert_eq!(ranges.lock().unwrap().len(), requests, "no new requests");
        let fresh = Icons::new(dir.path()).with_packs([(
            "aws".to_owned(),
            IconPack {
                url: "http://127.0.0.1:9/x.zip".into(),
            },
        )]);
        assert!(
            fresh
                .resolve(&IconSource::Pack("aws/bigquery.png".into()))
                .await
                .is_none(),
            "index cached per URL"
        );
        assert!(
            icons
                .resolve(&IconSource::Pack("aws/bigquery.png".into()))
                .await
                .is_some(),
            "index reused from disk"
        );
        assert!(
            icons
                .resolve(&IconSource::Pack("gcp/x.png".into()))
                .await
                .is_none(),
            "unknown pack"
        );
    }
}
