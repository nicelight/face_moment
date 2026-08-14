# Papercuts

- The installed `playwright cli` executable did not include its default
  `chrome-for-testing` browser binary; the first `open` failed and required the
  explicit project-prescribed `playwright cli install-browser chrome-for-testing`
  bootstrap before real-browser verification could start.
- `playwright cli run-code` did not expose the Node `URL` global inside its
  evaluated callback; a response listener using `new URL(...)` failed after
  browser interaction began. Direct pathname-suffix comparison avoids this
  non-obvious CLI evaluation constraint.
