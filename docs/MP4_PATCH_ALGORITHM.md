# MP4 timing patch – algorithm

Goal: slow playback by ratio r = p/q (60→30 FPS is r = 2) without changing any encoded sample.

1. **Parse** boxes by header only (32/64-bit sizes, size 0, uuid). Reject fragmented MP4 (moof/sidx/mvex), missing moov, inconsistent stts/stsz.
2. **Plan** every edit as a fixed-width, in-place number change at a parsed offset (so no stco/co64 offset ever moves):
   * per track, if `timescale·q` is divisible by `p`: *timescale mode* – `mdhd.timescale = ts·q/p`; sample tables stay byte-identical.
   * otherwise *delta mode* – `timescale = ts·q`; `stts` deltas, `ctts` offsets, `elst.media_time`, `mdhd.duration` × p. (`cslg` in this mode is rejected.)
   * movie-timescale values (`mvhd.duration`, `tkhd.duration`, `elst.segment_duration`) × r, rounded half-up.
   * mvhd/mdhd/tkhd/elst versions 0 and 1 handled; overflow of a field aborts.
3. **Copy** the source in 8 MB chunks to `<out>.part`, then apply the writes.
4. **Audio** (if present): FFmpeg produces a slowed AAC stream (`asetrate`+`aresample`, pitch drops like the video). It is grafted natively: old `moov` becomes a `free` box in place, new `mdat` (audio) + new `moov` are appended; video chunk offsets stay valid. Alternatively the audio trak is dropped.
5. **Validate** (independent re-parse): structure; frame count; exact duration and FPS (rational arithmetic); stsz/stco/stsc/stss/stsd tables; every byte outside the patched fields identical (no audio) or SHA-256 of all video samples identical (with audio); A/V offset drift; FFprobe cross-check.
6. Only after validation passes is `.part` renamed to the final name. The source is never opened for writing.
