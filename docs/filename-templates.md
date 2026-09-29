# Filename templates

Templates control how Tidekeeper names folders and files. Each label in braces
is replaced with information from TIDAL. For example,
`{TrackNumber} - {ArtistName} - {TrackTitle}` becomes
`03 - Example Artist - Example Track`.

Change templates in the desktop app under **Settings → Naming**, or in the
terminal menu under option **4**. Enter `default` in the terminal to restore a
template.

## Defaults

| Template | Default |
| --- | --- |
| Album folder | `{ArtistName}/{Flag} {AlbumTitle} [{AlbumID}] [{AlbumYear}]` |
| Playlist folder | `Playlist/{PlaylistName} [{PlaylistUUID}]` |
| Track file | `{TrackNumber} - {ArtistName} - {TrackTitle}{ExplicitFlag}` |
| Video file | `{VideoNumber} - {ArtistName} - {VideoTitle}{ExplicitFlag}` |

- Use `/` to create subfolders on every platform.
- File extensions are added automatically.
- Characters that aren't allowed in filenames are replaced, so a folder can never
  end up outside your download folder.
- Albums with several discs get `CD1`, `CD2`, and so on subfolders.
- Videos without an album are saved in a `Video` folder.
- When downloading in Atmos, `[Dolby Atmos]` is added to track names unless the
  template already uses `{StreamQuality}` or `{Codec}`.

## Labels

✓ means the label works in that template. Leave out labels that a template
doesn't support.

| Label | Meaning | Album folder | Track file | Video file | Playlist folder |
| --- | --- | :---: | :---: | :---: | :---: |
| `{ArtistName}` | All album artists, or the main track/video artist | ✓ | ✓ | ✓ | |
| `{ArtistsName}` | All track or video artists | | ✓ | ✓ | |
| `{ArtistID}` | IDs of all artists | ✓ | ✓ | ✓ | |
| `{AlbumArtistName}` | Main album artist | ✓ | | | |
| `{AlbumArtistID}` | Main album artist ID | ✓ | | | |
| `{TrackArtistName}` | Main track artist | | ✓ | | |
| `{TrackArtistID}` | Main track artist ID | | ✓ | | |
| `{VideoArtistName}` | Main video artist | | | ✓ | |
| `{VideoArtistID}` | Main video artist ID | | | ✓ | |
| `{AlbumTitle}` | Album title | ✓ | ✓ | | |
| `{AlbumID}` | Album ID | ✓ | | | |
| `{AlbumYear}` | Album release year | ✓ | ✓ | | |
| `{ReleaseDate}` | Album release date | ✓ | | | |
| `{RecordType}` | Album, EP, or single | ✓ | | | |
| `{Flag}` | `M` Master, `A` Dolby Atmos, `E` explicit, for example `[E]` | ✓ | | | |
| `{NumberOfTracks}` | Number of album tracks | ✓ | | | |
| `{NumberOfVideos}` | Number of album videos | ✓ | | | |
| `{NumberOfVolumes}` | Number of album discs | ✓ | | | |
| `{TrackTitle}` | Track title, with its version if any | | ✓ | | |
| `{TrackNumber}` | Track number, two digits | | ✓ | | |
| `{TrackID}` | Track ID | | ✓ | | |
| `{ExplicitFlag}` | `(Explicit)` for explicit items | | ✓ | ✓ | |
| `{AudioQuality}` | Best quality TIDAL lists for the item | ✓ | ✓ | | |
| `{StreamQuality}` | Quality actually downloaded, such as `Max` | | ✓ | | |
| `{Codec}` | Audio codec, such as `flac` | | ✓ | | |
| `{Duration}` | Length as `MM-SS` or `H-MM-SS` | ✓ | ✓ | | |
| `{DurationSeconds}` | Length in seconds | ✓ | ✓ | | |
| `{VideoTitle}` | Video title | | | ✓ | |
| `{VideoNumber}` | Video number, two digits | | | ✓ | |
| `{VideoID}` | Video ID | | | ✓ | |
| `{VideoYear}` | Video release year | | | ✓ | |
| `{PlaylistName}` | Playlist name | | | | ✓ |
| `{PlaylistUUID}` | Playlist ID | | | | ✓ |
