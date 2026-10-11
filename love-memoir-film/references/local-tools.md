# 本地工具用法

助手运行工具即可，新手不必敲命令。以下命令从本 Skill 文件夹执行；python 表示当前环境可用的 Python 3.10 或更新版。除了媒体处理需要的 FFmpeg/ffprobe，脚本不需要 pip 包。缺依赖时如实提示，由用户或宿主安装，不偷偷下载执行程序。

```text
python scripts/filmkit.py init ./my-film --title "我们的回忆"
python scripts/filmkit.py probe ./my-film/media/source.mp4
python scripts/filmkit.py contact ./my-film/media/source.mp4 --out ./my-film/review/source --step 0.5
python scripts/filmkit.py contact ./my-film/media/source.mp4 --out ./my-film/review/transition --start 4 --end 5 --step 0.041666667
python scripts/filmkit.py board ./my-film/brief.json --out ./my-film/制作工作台.html
python scripts/filmkit.py check ./my-film/edit-plan.json
python scripts/filmkit.py render ./my-film/edit-plan.json --out ./my-film/output/film-v1.mp4
python scripts/selftest.py
```

init 创建空 brief.json、媒体/提示词/审查/输出目录与编辑清单示例，不伪造实际素材。路径含空格时作为一个参数传入。项目文件可相对路径或当前机器绝对路径；公开分享前删掉个人路径。
contact 输出图片、来源时间码及离线HTML；步长只能说明抽样密度，不能证明已经人工看过。示例4到5秒必须落在真实片段内。每次用新的输出目录。
board 读取 brief 中的 title、idea、assets、must_keep、must_exclude、units。每个 unit 可含 id、title、seconds、status、references、prompt_zh、prompt_en。显示状态原样保留，复制按钮不提交生成。见[完整示例](../assets/brief-example.json)。

## 编辑清单
schema_version=1；width、height为正偶数；fps为整数；fit为contain或cover。contain等比加边，cover等比放大居中裁切，使用cover前检查人物/手是否被裁掉。
clips每项：file、in（源入点秒）、frames（输出整数帧）、speed（默认1，明确选择才变速）、purpose。所需源时长=frames/fps×speed。切点均为基础硬切；复杂遮挡/叠化必须先做成视频。
music可设null表示无声导出；填写时含file、in、gain_db、fade_out_seconds、allow_silence。allow_silence默认false，短音频会拒绝；true只在允许补静音时使用。

**声音限制：此基础渲染器不保留每个源视频的现场声。** 它仅合入指定音乐，且编码为AAC，不承诺原音乐包哈希不变。需要对白、现场声、多轨混音、音频无损复制时用宿主编辑工具或专门写时间线，不用此脚本冒充完成。
输出已有文件会拒绝，不覆盖。技术检查报告中的visual_review仍是pending、audio_listening是not performed；助手应另记实际审查结论，不能改成并未执行的已试听。
不包含任何视频模型调用或自动收费；不生成手、脸或运镜，不自动“修好”转场。
