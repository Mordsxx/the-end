# AI model installation

The GitHub build downloads everything automatically. For running from source / manual setup:

1. Download `rife-ncnn-vulkan-<date>-windows.zip` from https://github.com/nihui/rife-ncnn-vulkan/releases
2. Extract it into the `models/` folder so you have `models/<any-folder>/rife-ncnn-vulkan.exe` next to the model folders (`rife-v4.6`, `rife-anime`, …).
3. Or point **Settings → RIFE folder** at the folder containing `rife-ncnn-vulkan.exe`.

Model notes: `rife-v4.x` supports any multiplier (2×–8×) in one pass; older models (`rife`, `rife-anime`, `rife-HD`, `rife-UHD`) double only.
Any new model folder containing `flownet.param` appears in the app automatically.
GPU: needs a Vulkan-capable GPU and a current driver. "CPU only" works but is extremely slow.
