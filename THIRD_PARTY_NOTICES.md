# Third-party notices

`src/amagi_vaultgraph/vendor/3d-force-graph.min.js` is the unmodified UMD build of
[3d-force-graph](https://github.com/vasturiano/3d-force-graph) v1.80.1
(npm `3d-force-graph@1.80.1`, `dist/3d-force-graph.min.js`,
sha256 `13088340 aad40815 6064fd12 0c3bc3a4 7c93a3cc 45b8f132 d6284b20 e2223be9`).
It is MIT licensed, Copyright (c) 2017 Vasco Asturiano; the full license is in
`src/amagi_vaultgraph/vendor/3d-force-graph.LICENSE`.

That build bundles its own dependencies, including [three.js](https://github.com/mrdoob/three.js)
(MIT); three-forcegraph, three-render-objects, float-tooltip, kapsule, accessor-fn,
data-bind-mapper and d3-force-3d (MIT, Vasco Asturiano); tinycolor2 (MIT); d3-array, d3-scale and
d3-scale-chromatic (ISC); and ngraph.graph and ngraph.forcelayout (BSD-3-Clause, Andrei Kashcha).
See each project's repository for its full license text.

The `--offline` HTML output (the default) inlines this file, so these notices apply to
generated HTML files as well.
