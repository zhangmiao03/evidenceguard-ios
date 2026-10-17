# 30 秒导览场景素材

四张室内素材使用内置 image_gen 生成并检查，作为网页交互演示，不是真实摄像头采集、模型输入或真实提醒证据。原始 PNG 保留在本机生成目录；这里只保存供页面使用的 WebP。使用 cwebp 1.3.2 以 quality 78 / method 6 做格式压缩，保持原始 1586 × 992 尺寸，不裁剪或重绘。门口场景沿用现有素材。

| 文件 | 状态 |
| --- | --- |
| PetBaseline.webp | 同一客厅，狗在关注区地毯外 |
| PetEntered.webp | 同一视角，狗进入地毯 |
| StudioBaseline.webp | 同一工作台，相机位于灰色垫子上 |
| StudioRemoved.webp | 同一视角，相机已离开原位置 |

参考画面、基线、变化和证据页都使用同一组配对素材，未将示意图或同一照片的文字变化当成真实检查结果。选框坐标以完整图像为基准；相机移动过程与十五秒有效观察跨度在此用脚本压缩展示。

## 生成与编辑提示词

### tour_pet_base

Use case: photorealistic-natural. Create a single realistic indoor home security-camera frame for a polished iOS app product demonstration, landscape 16:10, 1536 x 960. Fixed elevated camera in upper front-left corner of a tasteful lived-in living room, slight wide angle but straight lines, natural soft daytime light, authentic photographic textures, everything in focus, no dramatic cinematic bokeh. Warm light oak floor, cream sofa along the back wall right of centre, beige textured cushions, a large low-pile rectangular light rug clearly visible on the floor directly in front of the sofa, plant by far-right window, low wood shelf on far left. A friendly medium-size golden retriever is near the LEFT edge on the exposed oak floor, outside the rug, at about x=14%, y=64%, fully visible but small. The entire rug foreground centre-right is EMPTY. The rug is the future monitored region spanning approx x=32% to 82%, y=52% to 91%. No coffee table or objects obstructing the rug. No people, no camera device in frame. Photographic realism and natural proportions, no cartoon, no vector, no UI, no frame, no annotations, no bounding boxes, no logos, no text or timestamps. This is an illustrative product-demo asset, not evidence.

### tour_studio_base

Use case: photorealistic-natural. Create ONE realistic home-studio security-camera image for a polished iOS app demonstration, landscape 16:10, 1536 x 960. Fixed camera mounted high at the front-left corner looking down toward a light oak work desk filling the lower two thirds of the image, gentle wide angle with straight architecture, everything in focus, natural daylight with soft real shadows. On the desk, a charcoal grey rectangular felt pad centered in the frame spans roughly x=35% to 76%, y=40% to 83%. A black compact mirrorless photographic camera with short black lens is placed near the exact centre of this pad, clearly recognizable at app-thumbnail size, body facing forward-left. Neutral warm white wall, closed silver laptop at far left corner of desk, tidy stack of notebooks at far right, small plant and desk lamp in the back corners. Balanced calm composition, plausible real photographic material texture, high resolution, restrained natural colors. No people, no security camera device, no duplicate photographic camera, no clutter. No text, branding, watermark, UI, diagrams, bounding boxes, timestamp, or phone frame. Product-demo illustration, not a real hardware recording. The pad and desk stay very clear for an edited follow-up frame with the camera removed.

### tour_pet_changed

Use case: precise-object-edit. The input image is the edit target: a realistic living room with a golden retriever OUTSIDE the rug. Create the follow-up frame of exactly the same fixed camera. Change ONLY the dog's position: move that same golden retriever to the centre-right part of the rug, roughly centre x=62%, paws y=74% of the image, fully within the rug, standing naturally and looking toward the camera. The dog should be clearly identifiable at phone-thumbnail size and physically correctly scaled, same coat and age. Remove the original dog completely from the far-left wood floor and reconstruct the exposed oak floor seamlessly. There must be exactly ONE dog in the image. Preserve every background feature, exact framing, camera angle, furniture position, rug edges, natural lighting, shadow direction and color palette. Maintain the original 1586 x 992 landscape aspect ratio. No text, timestamps, overlays, watermark, logos, UI or bounding boxes. Natural photographic material and anatomy. This is an AI-rendered scenario demo asset, not real surveillance evidence.

### tour_studio_changed

Use case: precise-object-edit. Input image is the edit target. Produce the follow-up frame from the identical fixed camera. ONLY remove the black photographic camera AND its short lens from the centre of the dark grey felt desk pad, including its shadow, and reconstruct the felt fabric with consistent texture and lighting. The entire dark pad should now be visibly empty. Keep the frame, crop, desk, laptop, notebooks, plants, lamp, chair, felt pad edges, sun/shadow lighting and every other pixel region as unchanged as possible. Same exact camera angle and 1586 x 992 landscape aspect ratio. Add no new objects or people. No text, timestamps, bounding boxes, logos, UI, or watermarks. Photographic realism. This is a generated product-demo before/after pair, not real evidence.


