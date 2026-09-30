# 媒体回归样本

`sample.mp4` 和 `sample.webm` 是本任务使用 FFmpeg 的 `color` 合成源生成的 32×24、0.5 秒绿色画面，分别采用 H.264 / VP8，无音轨、无外部素材或版权依赖。仅用于容器与上传回归，不代表全部浏览器编码兼容验收。

`valid-webp-multibyte-length.webp` 为审查时用 Pillow 生成的 256×256 合成样本（34,790 字节），RIFF 长度含 `de87` 字节序列，用于防止把二进制文件头按 UTF-8 字符索引读取的回归。
