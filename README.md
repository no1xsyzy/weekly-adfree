# weekly-adfree

**测试中**

对[阮一峰的周刊](https://github.com/ruanyf/weekly)进行处理，使用朴素贝叶斯的方式对其中的广告进行过滤。

阮一峰的周刊是**开源**的，意味着任何人都被明确授予了后期处理并分享修改后的版本的权利。

## 使用方式

需求：
  - [git](https://git-scm.com/)
  - [python](https://www.python.org/)
  - [poetry](https://python-poetry.org/)

```bash
# 拉取 repo
git clone https://github.com/no1xsyzy/weekly-adfree.git
cd weekly-adfree
git submodule init

# 安装工具及依赖
poetry install

# 同步周刊（周刊更新后需要再次同步）
git submodule update --remote

# 处理全部
poetry run python process.py proc-all
```
