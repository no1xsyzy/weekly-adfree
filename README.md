# weekly-adfree

**测试中**

对[阮一峰的周刊](https://github.com/ruanyf/weekly)进行处理，使用朴素贝叶斯的方式对其中的广告进行过滤。

阮一峰的周刊是**开源**的，意味着任何人都被明确授予了后期处理并分享修改后的版本的权利。

## 简单使用

你可以使用[这个RSS地址订阅](https://github.com/no1xsyzy/weekly-adfree/raw/master/rss.xml)。

## 更新方式

### 依赖
  - [git](https://git-scm.com/)
  - [python](https://www.python.org/)
  - [poetry](https://python-poetry.org/)

### 安装（每台机器完成一次即可）
```bash
# 拉取 repo
git clone https://github.com/no1xsyzy/weekly-adfree.git
cd weekly-adfree

# 拉取周刊内容
git submodule init

# 安装工具及依赖
poetry install
```

### 更新（每当周刊更新就需要运行一次）
```bash
# 同步周刊（周刊更新后需要再次同步）
git submodule update --remote

# 处理全部
poetry run python process.py proc-all
```

## 计划
- [x] 性能优化
- [x] RSS
- [ ] GitHub Actions 自动化
