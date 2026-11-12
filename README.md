# Photo Sorter

Aplikasi Windows for sorting photos. Current version: **0.3.0 beta**.
The interface features a *hand-drawn* style, with colors resembling paper and sketch-like lines.

## How to Access the Application

Download `PhotoSorter.exe` from the **Releases** section on GitHub, then open the file. No Python installation is required.

## Releases

Save code changes to the repository, then create and push a new version tag—for example, `v0.3.1-beta`. A GitHub Actions *workflow* will build the Windows EXE file and attach it to a GitHub Release. Tags containing a hyphen (`-`) will be published as a *prerelease*. This *workflow* can also be triggered manually via the **Actions** tab by entering the tag name.

Within the application, click **Check for updates** in the main menu. If a newer version is available, the application will open the release page, allowing the user to download the EXE file.

Update checks are performed by querying the GitHub API for public releases of `PaleSalome/PhotoSorter`. The application does not automatically download or replace the EXE file.

The sorting interface adapts to the window size and screen resolution; the saved window size is constrained to ensure it remains within the screen boundaries.

Canon RAW photo format (`.CR3`) is also supported via `rawpy`/LibRaw.
