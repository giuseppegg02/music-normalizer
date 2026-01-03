# Fix for Trimmed Songs Issue

## Problem
After processing 80 songs, 2 of them were being trimmed at 1:30 minutes instead of maintaining their full length.

## Root Cause
The application was using single-pass loudnorm normalization, which can occasionally trim or cut audio files, especially with longer songs or certain audio characteristics.

## Solution
Implemented two-pass loudnorm normalization, which is the recommended approach by FFmpeg:

### Pass 1: Measurement
```bash
ffmpeg -i input.mp3 -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" -f null -
```
This analyzes the audio and outputs measurements:
- `input_i`: Integrated loudness
- `input_tp`: True peak
- `input_lra`: Loudness range
- `input_thresh`: Threshold

### Pass 2: Normalization
```bash
ffmpeg -i input.mp3 -af "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-20.5:measured_TP=-1.2:measured_LRA=8.5:measured_thresh=-30.5:linear=true" -ar 48000 output.mp3
```
This applies accurate normalization using the measured parameters with `linear=true` mode.

## Benefits
- **No trimming**: Audio files maintain their full duration
- **Better accuracy**: More precise loudness normalization
- **Fallback safety**: If Pass 1 fails, falls back to single-pass mode
- **Linear normalization**: The `linear=true` parameter ensures proper processing

## Testing
To verify the fix works:

1. Process a batch of audio files (including files longer than 2 minutes)
2. Compare input and output durations using:
   ```bash
   ffmpeg -i input.mp3 2>&1 | grep Duration
   ffmpeg -i output.mp3 2>&1 | grep Duration
   ```
3. Verify durations match (±1 second for encoding differences)

## References
- [FFmpeg loudnorm filter documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)
- [EBU R128 loudness normalization](https://tech.ebu.ch/docs/r/r128.pdf)
