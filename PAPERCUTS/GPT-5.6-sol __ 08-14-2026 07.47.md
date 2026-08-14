- A verifier probe mounted at `/tmp` could import the installed application but
  not the packaged `/app/tests` tree because Python set `sys.path[0]` to
  `/tmp`. Add `/app` explicitly for packaged test-helper imports; this does not
  add `/app/src` or replace the installed application package.
