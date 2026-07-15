# AUR packaging

There are two AUR packages so Arch/EndeavourOS/Manjaro users can install with
`yay` and get dependencies and updates handled for them:

- **`fileconverter`** follows tagged releases. The release workflow pushes an
  update on every `vX.Y.Z` tag.
- **`fileconverter-git`** builds from `main` and figures out its own version at
  build time, so it doesn't need a push for every commit.

Both build the Python package from source and pull ffmpeg, ImageMagick and the
rest in as pacman dependencies. Building on the user's machine is also why this
avoids the prebuilt-binary problem from issue #6 — there's no bundled binary to
clash with the system libraries.

Once it's installed, each user sets up their own right-click menu:

```bash
fileconverter --install     # fileconverter --uninstall to remove it
```

## Auto-publishing the stable package

`.github/workflows/release.yml` has a `publish-aur` job that pushes the
`fileconverter` package whenever a non-prerelease tag goes out. It does nothing
until you add the AUR credentials, so it won't break anything before then. To
turn it on, add three repository secrets (Settings → Secrets and variables →
Actions):

| Secret | What goes in it |
|---|---|
| `AUR_USERNAME` | the AUR account username |
| `AUR_EMAIL` | the email on that account |
| `AUR_SSH_PRIVATE_KEY` | a private SSH key whose public half is on the account |

The job sets the version from the tag, runs `updpkgsums` for the checksum,
regenerates `.SRCINFO`, and pushes. `fileconverter-git` versions itself, so you
only need to publish it once by hand.

## Doing it by hand

On an Arch box with an AUR account:

```bash
git clone ssh://aur@aur.archlinux.org/fileconverter.git
cd fileconverter
cp /path/to/Media-Converter/packaging/aur/fileconverter/PKGBUILD .
# for a release, set pkgver to the tag first, then:
updpkgsums
makepkg --printsrcinfo > .SRCINFO
makepkg -si    # build and install to check it works
git add PKGBUILD .SRCINFO && git commit -m "Update to vX.Y.Z" && git push
```

Same steps for `fileconverter-git` (its `pkgver()` handles the version for you).

## A couple of notes

- The package is named after the tool (`fileconverter`), not the repo
  (`media-converter`), which is the usual AUR convention. Check the name is
  free before the first push and change it in both PKGBUILDs and the workflow
  if it isn't.
- The GUI libraries (`python-gobject`, `gtk4`, `libadwaita`, `tk`) are
  `optdepends`. Conversions run fine without them — the UI falls back to
  tkinter, then to headless.
