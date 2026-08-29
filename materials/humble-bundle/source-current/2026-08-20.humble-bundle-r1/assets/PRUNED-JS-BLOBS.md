# Pruned JavaScript blobs

The frozen build strips every `<script>` from the captured DOM, so no
captured JavaScript bundle is ever referenced by a clone page or shipped
as an asset. The 10 captured JS bundles were therefore removed from this
capture pool: they carried third-party client configuration values and
open-source library author contact lines, and the repository must not
persist credential-shaped values it has no use for. No claim in
`scope/claims.jsonl` cites a JavaScript blob; the pages, their CSS, fonts
and images are unaffected.
