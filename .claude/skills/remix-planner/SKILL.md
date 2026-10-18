---
name: remix-planner
description: Turn a vague music request ("trending Bollywood songs", "something chill for a party") into a concrete, downloaded and analyzed shortlist of songs without asking the user for details. Use in track-scout.
---

# Remix planner

Goal: from any request, however vague, end with N real, downloaded, analyzed songs. Work in four stages and checkpoint each (`interpret`, `research`, `shortlist`, `candidate_N`).

## 1. Interpret (`interpret`)

Extract what you can, fill the rest with defaults, and record every default with `state_add_assumption`.

| Detail | Default |
| --- | --- |
| Songs named by the user | If any are named, skip research and use exactly those |
| Region and genre | Bollywood or "Hindi" means region India, genre Bollywood. Punjabi, Tamil, Telugu, Kannada, K-pop and similar map to their own genre with the matching region. Otherwise use the genre as given, region "global" |
| "Trending", "latest", "popular" | The current top of the charts, this month |
| Count | Mashup or medley: 4 songs. Set: duration in minutes divided by 3.5. Layered mashup of two named songs: 2 |
| Mood | Upbeat, unless the user says otherwise |

Checkpoint `interpret` with `{region, genre, count, mood, named_songs}`.

## 2. Research (`research`)

Only when the user did not name every song.

1. Call `find_trending(region, genre, limit=8)`.
2. Read the titles, snippets and `page_excerpt` text. Pull out real song titles with artists (for example "Kesariya, Arijit Singh"). Prefer songs that appear on more than one source. Ignore playlists, "top 10" headings, and non-song lines.
3. Collect at least `count + 2` titles, ordered by how often and how high they appear.
4. If the charts give too few titles, call `find_trending` again with a broader genre or region, or fall back to `search_song("top {genre} songs this month")` and read the titles. Never stop and ask the user.

Checkpoint `research` with `{titles: [...]}`.

## 3. Shortlist and fetch (`shortlist`, `candidate_N`)

For each title, in order, until you have `count` good songs:

1. `search_song("{title} {artist} official audio", limit=3)`. Prefer an official audio or lyric-video upload. Skip live versions, "slowed", "reverb", "8D", "remix", "cover", and anything that looks like a compilation.
2. `download_song(url)`. If the returned duration is over 30 minutes or the download fails, take the next result or the next title.
3. `analyze_track(track_id)`. If BPM is 0 or the track is under 60 seconds, discard it and take the next title.
4. Checkpoint `candidate_N` with `{track_id, title, bpm, key, camelot, energy, duration}`. Energy is the average of the section energies.

Downloads are slow, so fetch only what you need: `count` songs plus replacements for failures, not a long extra list.

If you cannot reach `count` songs after trying every title, continue with what you have as long as it is at least 2, and record that as an assumption. With fewer than 2, fail the step with a plain-language error.

## 4. Hand over

Return a short table (title, BPM, key, energy) and the list of assumptions. Final message format:

```
STATUS: done
CANDIDATES: <track_id>, <track_id>, ...
```
