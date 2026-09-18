# Contributing

Bug reports and focused pull requests are welcome. Keep changes source-grounded,
preserve the typed API contracts, and do not add private documents, credentials,
model weights, or generated runtime directories.

Before opening a pull request, run:

```bash
./run-verinice --test
cd frontend
npm run lint
node scripts/verify-walkthrough.mjs
npm run build
```

Changes to recorded outputs must be produced through
`./run-verinice --record-walkthrough`; do not hand-edit them. New third-party
data must include its source, applicable licence or use terms, retrieval date,
and transformation notes.
