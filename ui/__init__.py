"""ui — QtWidgets 界面层。

这里可以 import Qt；``core/`` 不允许（那样才能脱离 GUI 单测）。

- ``controller``  界面状态 + 全部业务操作，不 import 任何 widget
- ``fields``      schema → 控件，字段新增不需要改这里的逻辑
- ``mainwindow``  QMainWindow：列表 / 表单 / 预览 / 按钮
"""
