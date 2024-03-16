def test_read():
    import pandoc
    pandoc.read('# Hello')


def test_read_14():
    from process import load_doc
    load_doc('weekly/docs/issue-14.md')
