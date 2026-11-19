# Deployment

## Build

The `build-windows` workflow (manual dispatch, or push a tag `workbench-v0.1.0`) installs Python 3.12, PyInstaller and pywebview, runs the tests, builds the application folder, starts it for eight seconds as a smoke test, zips it, and tries to build an Inno Setup installer. Artifacts are attached to the run, and to the release when a tag triggered it.

Local build on Windows:

```
pip install pyinstaller pywebview
pyinstaller packaging/workbench.spec --noconfirm
```

## Offline use

Review of existing results, item browsing, report export and simulated runs need no network. Real runs need the provider's network, or a local endpoint.

## Updating item banks and results

Item and results files are bundled at build time. Users add banks through the import form, and runs are stored in their profile.

## Code signing

Not done. Unsigned builds trigger SmartScreen warnings. A partner organisation that distributes the application widely should sign it.

## Support boundary

Pilot software, provided as is, under the repository licence.
