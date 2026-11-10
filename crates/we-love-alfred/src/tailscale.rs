//! Reachable tailnet services as items.

use std::collections::BTreeMap;
use std::time::Duration;

use futures_util::future;
use reqwest::Client;
use serde::Deserialize;

use crate::shell::{output, tool};
use crate::{Item, ItemBuilder, Result};

/// The `[tailscale]` config table.
///
/// ```toml
/// [tailscale]
/// tag = "tag:k8s"                       # peers with this tag become links, if they answer
/// exclude = ["old-mac-mini"]
/// routes = true                         # also list subnet-route gateways
/// paths = { haproxy = [":8404/stats"] } # extra links per hostname
/// ```
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tailscale {
    pub tag: Option<String>,
    #[serde(default)]
    pub exclude: Vec<String>,
    #[serde(default)]
    pub routes: bool,
    #[serde(default)]
    pub paths: BTreeMap<String, Vec<String>>,
}

#[derive(Debug, Deserialize)]
struct Status {
    #[serde(rename = "Peer", default)]
    peers: BTreeMap<String, Peer>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "PascalCase")]
struct Peer {
    host_name: String,
    #[serde(rename = "DNSName")]
    dns_name: String,
    #[serde(default)]
    tags: Vec<String>,
    #[serde(default)]
    primary_routes: Vec<String>,
    online: bool,
}

impl Peer {
    fn host(&self) -> &str {
        self.dns_name.trim_end_matches('.')
    }
}

impl Tailscale {
    /// Items for peers from `tailscale status`, probed concurrently; nothing when tailscale isn't running.
    ///
    /// # Errors
    ///
    /// [`Error::Http`] only if the probe client can't be built.
    pub async fn items(&self) -> Result<Vec<ItemBuilder>> {
        let Ok(status) = output(
            tool("tailscale").args(["status", "--json"]),
            Duration::from_secs(5),
        )
        .await
        else {
            return Ok(Vec::new());
        };
        let Ok(status) = serde_json::from_str::<Status>(&status) else {
            return Ok(Vec::new());
        };
        self.items_for(status.peers.into_values().collect()).await
    }

    async fn items_for(&self, peers: Vec<Peer>) -> Result<Vec<ItemBuilder>> {
        let mut items = Vec::new();
        if self.routes {
            for peer in peers
                .iter()
                .filter(|p| p.online && !p.primary_routes.is_empty())
            {
                let routes = peer.primary_routes.join(", ");
                items.push(
                    Item::url(
                        format!("ts route — {}", peer.host_name),
                        format!("https://{}", peer.host()),
                    )
                    .subtitle(format!("routes: {routes}"))
                    .match_text(format!("tailscale route {} {routes}", peer.host_name)),
                );
            }
        }
        let Some(tag) = &self.tag else {
            return Ok(items);
        };
        let tagged: Vec<&Peer> = peers
            .iter()
            .filter(|p| p.online && p.tags.contains(tag) && !self.exclude.contains(&p.host_name))
            .collect();
        let client = Client::builder()
            .timeout(Duration::from_millis(500))
            .build()?;
        let schemes =
            future::join_all(tagged.iter().map(|peer| reachable(&client, peer.host()))).await;
        for (peer, scheme) in tagged.into_iter().zip(schemes) {
            let Some(scheme) = scheme else { continue };
            let base = format!("{scheme}://{}", peer.host());
            items.push(Item::url(&peer.host_name, &base));
            for path in self.paths.get(&peer.host_name).into_iter().flatten() {
                items.push(Item::url(&peer.host_name, format!("{base}{path}")));
            }
        }
        Ok(items)
    }
}

/// The first of https and http to answer without an error status.
async fn reachable(client: &Client, host: &str) -> Option<&'static str> {
    let probe = |scheme: &'static str| {
        let request = client.get(format!("{scheme}://{host}")).send();
        Box::pin(async move {
            match request.await {
                Ok(r) if !r.status().is_client_error() && !r.status().is_server_error() => {
                    Ok(scheme)
                }
                _ => Err(()),
            }
        })
    };
    future::select_ok([probe("https"), probe("http")])
        .await
        .ok()
        .map(|(scheme, _)| scheme)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn lists_routes_and_skips_unreachable_or_excluded_peers() {
        let status: Status = serde_json::from_str(
            r#"{"Peer": {
                "a": {"HostName": "gw", "DNSName": "gw.ts.net.", "PrimaryRoutes": ["10.0.0.0/8"], "Online": true},
                "b": {"HostName": "dead", "DNSName": "127.0.0.1:9.", "Tags": ["tag:k8s"], "Online": true},
                "c": {"HostName": "skip", "DNSName": "skip.ts.net.", "Tags": ["tag:k8s"], "Online": true},
                "d": {"HostName": "off", "DNSName": "off.ts.net.", "Tags": ["tag:k8s"], "Online": false}
            }}"#,
        )
        .unwrap();
        let config = Tailscale {
            tag: Some("tag:k8s".into()),
            exclude: vec!["skip".into()],
            routes: true,
            ..Tailscale::default()
        };
        let titles: Vec<String> = config
            .items_for(status.peers.into_values().collect())
            .await
            .unwrap()
            .into_iter()
            .map(|i| i.title)
            .collect();
        assert_eq!(titles, ["ts route — gw"]);
    }
}
