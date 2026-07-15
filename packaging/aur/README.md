# AUR packaging

Two [AUR](https://aur.archlinux.org/) packages let Arch/EndeavourOS/Manjaro
users install with `yay -S …` and get automatic dependency resolution and
updates:

| Package | Tracks | Update cadence |
|---|---|---|
| [`fileconverter`](fileconverter/PKGBUILD) | tagged releases | on every `vX.Y.Z` tag (via CI) |
| [`fileconverter-git`](fileconverter-git/PKGBUILD) | `main` | self-versions at build time, no push needed |

Both build the Python package from source and install the `fileconverter`,
`fileconverter-pick` and `fileconverter-install` commands system-wide. The
media tools (ffmpeg, ImageMagick, and optionally Ghostscript/LibreOffice) come
in as pacman dependencies — so building from source on Arch sidesteps the
prebuilt-binary library mismatch reported in issue #6.

After installing, each user sets up their own right-click menu with:

```bash
fileconverter --install     # and: fileconverter --uninstall
```

## Automatic publishing of the stable package

`.github/workflows/release.yml` has a `publish-aur` job that pushes the
`fileconverter` package to the AUR on every non-prerelease tag. It stays
**skipped** until the AUR credentials are configured, so nothing breaks before
then. To enable it, add three repository secrets (Settings → Secrets and
variables → Actions):

| Secret | Value |
|---|---|
| `AUR_USERNAME` | the AUR account's username |
| `AUR_EMAIL` | the email on that AUR account |
| `AUR_SSH_PRIVATE_KEY` | a private SSH key whose public half is registered on the AUR account |

The job sets `pkgver` from the tag, runs `updpkgsums` to fill in the source
checksum, regenerates `.SRCINFO`, and pushes. `fileconverter-git` needs no
per-release push (it self-versions), so publish it once by hand.

## Publishing by hand

On an Arch machine with an AUR account set up:

```bash
git clone ssh://aur@aur.archlinux.org/fileconverter.git aur-fileconverter
cd aur-fileconverter
cp /path/to/Media-Converter/packaging/aur/fileconverter/PKGBUILD .
# for a release, pin pkgver to the tag, then:
updpkgsums                       # fills in sha256sums
makepkg --printsrcinfo > .SRCINFO
makepkg -si                      # build + install locally to test
git add PKGBUILD .SRCINFO && git commit -m "Update to vX.Y.Z" && git push
```

Same flow for `fileconverter-git` (its `pkgver()` fills the version in
automatically; just publish it once).

## Notes

- Package name follows the upstream tool name (`fileconverter`), not the repo
  name (`media-converter`), per AUR convention. Verify the name is free on the
  AUR before the first push; rename in both PKGBUILDs and the workflow if not.
- The GUI dependencies (`python-gobject`, `gtk4`, `libadwaita`, `tk`) are
  `optdepends`: conversions run headless without them, and the tool falls back
  from GTK → tkinter → headless.
