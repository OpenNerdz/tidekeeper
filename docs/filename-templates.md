# Filename templates

Tidekeeper can organize downloads and build filenames from information about
the album, track, video, or playlist. A label inside braces is replaced when a
file or folder is created.

For example:

```text
{TrackNumber} - {ArtistName} - {TrackTitle}
```

could become:

```text
03 - Example Artist - Example Track
```

The default templates are suitable for most users. You can change them in the
desktop Settings panel or in the terminal's full settings menu.

## Available labels

| Label | Meaning | Album | Track | Video | Playlist |
| --- | --- | :---: | :---: | :---: | :---: |
| `{ArtistID}` | IDs for all artists | Yes | Yes | Yes | No |
| `{ArtistName}` | All album artists, or the primary track/video artist | Yes | Yes | Yes | No |
| `{ArtistsName}` | Names of all track or video artists | No | Yes | Yes | No |
| `{AlbumArtistID}` | Primary album artist ID | Yes | No | No | No |
| `{AlbumArtistName}` | Primary album artist name | Yes | No | No | No |
| `{TrackArtistID}` | Primary track artist ID | No | Yes | No | No |
| `{TrackArtistName}` | Primary track artist name | No | Yes | No | No |
| `{VideoArtistID}` | Primary video artist ID | No | No | Yes | No |
| `{VideoArtistName}` | Primary video artist name | No | No | Yes | No |
| `{Flag}` | Content flags such as Master, Atmos, or Explicit | Yes | No | No | No |
| `{AlbumID}` | Album ID | Yes | No | No | No |
| `{AlbumYear}` | Album release year | Yes | Yes | No | No |
| `{AlbumTitle}` | Album title | Yes | Yes | No | No |
| `{AudioQuality}` | Audio quality reported by TIDAL | Yes | Yes | No | No |
| `{DurationSeconds}` | Duration in seconds | Yes | Yes | No | No |
| `{Duration}` | Duration as `MM:SS` or `H:MM:SS` | Yes | Yes | No | No |
| `{NumberOfTracks}` | Number of album tracks | Yes | No | No | No |
| `{NumberOfVideos}` | Number of album videos | Yes | No | No | No |
| `{NumberOfVolumes}` | Number of album volumes | Yes | No | No | No |
| `{ReleaseDate}` | Release date | Yes | No | No | No |
| `{RecordType}` | Album record type | Yes | No | No | No |
| `{TrackID}` | Track ID | No | Yes | No | No |
| `{TrackNumber}` | Track number | No | Yes | No | No |
| `{TrackTitle}` | Track title | No | Yes | No | No |
| `{ExplicitFlag}` | Explicit-content marker | No | Yes | Yes | No |
| `{StreamQuality}` | Quality of the selected stream | No | Yes | No | No |
| `{Codec}` | Audio codec | No | Yes | No | No |
| `{VideoID}` | Video ID | No | No | Yes | No |
| `{VideoNumber}` | Video number | No | No | Yes | No |
| `{VideoTitle}` | Video title | No | No | Yes | No |
| `{VideoYear}` | Video release year | No | No | Yes | No |
| `{PlaylistUUID}` | Playlist ID | No | No | No | Yes |
| `{PlaylistName}` | Playlist name | No | No | No | Yes |

Not every label is available for every type of download. If a label is not
supported in that context, leave it out of that template.
