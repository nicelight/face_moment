# Papercuts

- A large mixed `apply_patch` update failed because two lines in the new report
  body lacked patch `+` prefixes. Split protocol and report changes into
  smaller patches and recheck each application.
