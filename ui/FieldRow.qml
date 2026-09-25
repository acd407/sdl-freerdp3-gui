import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 一行表单字段，按 fld.widget 选择控件。
//
// 三个必须注意的点（都是实测踩出来的）：
//
//  1. `required property var fld` 是在 finalize 阶段才被赋值的，而**同一对象上的
//     其他属性绑定可能更早求值一次**，那时 fld 还是 undefined，会刷一片
//     "TypeError: Value is undefined…"。所以这里一律通过 `F` 访问，它保证是对象。
//
//  2. QML 的 TextField/SpinBox 在用户输入时会自己给属性赋值，从而**打断**
//     `text:` / `value:` 的绑定。所以不在声明里绑定，而在 sync() 里显式同步。
//
//  3. 每个控件只能被喂自己类型的数据。把字符串 Number() 成 NaN 塞给 SpinBox
//     （它的 value 是 int）会让 Qt 直接 abort。所以 sync() 按 widget 分派。
RowLayout {
    id: root
    // 独立组件文件作为 Repeater 的 delegate 时，index/modelData 不会自动注入，
    // 必须像这样声明为 required property，QML 才会赋值。
    required property int index
    required property var fld

    // 恒为对象的访问器，避免 fld 尚未赋值时的绑定报错
    readonly property var f: fld !== undefined && fld !== null ? fld : ({})
    property string key: f.key !== undefined ? String(f.key) : ""
    property bool syncing: false

    readonly property bool isText: f.widget === "text" || f.widget === "path"
    readonly property bool isInt: f.widget === "int"
    readonly property bool isBool: f.widget === "bool"
    readonly property bool isEnum: f.widget === "enum"
    // 文本控件要撑满，其余控件左对齐
    readonly property bool showFiller: !isText

    spacing: 10

    Label {
        // preferredWidth 实测就是 Layout 对该标签生效的最小宽度（再给
        // Layout.minimumWidth 更小的值也不会让它收缩），所以这一列是固定的。
        // 相应地 Main.qml 右侧面板的 minimumWidth 必须 >= 本行所需宽度
        // （190 + 间距 + 控件最小宽度），否则窄窗口下各行会溢出出横向滚动条。
        Layout.preferredWidth: 190
        Layout.alignment: Qt.AlignTop
        text: root.f.label !== undefined ? String(root.f.label) : ""
        wrapMode: Text.WordWrap

        HoverHandler { id: hover }
        ToolTip.visible: hover.hovered && String(root.f.help !== undefined ? root.f.help : "").length > 0
        ToolTip.text: String(root.f.help !== undefined ? root.f.help : "")
        ToolTip.delay: 400
    }

    TextField {
        id: textCtl
        visible: root.isText
        Layout.fillWidth: true
        onEditingFinished: if (!root.syncing) bridge.setField(root.key, text)
    }

    SpinBox {
        id: intCtl
        visible: root.isInt
        // 宽窗口保持 170 的观感，窄窗口必须能继续收缩。
        //
        // 只给 preferredWidth 的控件会把自己的 preferred 当成**最小宽度**卡住
        // 整行：行内最小宽度 = 190(标签) + 控件 preferred + 间距。窗口一窄，
        // 这些行就停在 490px 不再收缩 → 表单比可视区宽 → 横向滚动条 + 右侧被裁切，
        // 而只有文本控件的行能正常收缩（实测 760px 窗口：连接组 486px，显示组 490px）。
        // 所以这里一律 fillWidth + maximumWidth：宽时不超过原宽度，窄时可收缩。
        Layout.fillWidth: true
        Layout.preferredWidth: 170
        Layout.maximumWidth: 170
        Layout.minimumWidth: 96
        editable: true
        from: root.f.minimum !== undefined ? root.f.minimum : 0
        to: root.f.maximum !== undefined ? root.f.maximum : 1000000
        onValueModified: if (!root.syncing) bridge.setField(root.key, value)
    }

    Label {
        visible: root.isInt && String(root.f.suffix !== undefined ? root.f.suffix : "").length > 0
        text: String(root.f.suffix !== undefined ? root.f.suffix : "")
    }

    CheckBox {
        id: boolCtl
        visible: root.isBool
        Layout.fillWidth: true
        onToggled: if (!root.syncing) bridge.setField(root.key, checked)
    }

    ComboBox {
        id: enumCtl
        visible: root.isEnum
        Layout.fillWidth: true
        Layout.preferredWidth: 280
        Layout.maximumWidth: 280
        Layout.minimumWidth: 120
        textRole: "text"
        valueRole: "value"
        onActivated: if (!root.syncing) bridge.setField(root.key, currentValue)
    }

    Item {
        Layout.fillWidth: root.showFiller
        visible: root.showFiller
    }

    function sync() {
        if (root.key === "")
            return
        var v = bridge.fields[root.key]
        if (v === undefined || v === null)
            v = root.F["default"]

        root.syncing = true
        if (root.isText) {
            textCtl.text = (v === undefined || v === null) ? "" : String(v)
        } else if (root.isInt) {
            var n = Number(v)
            if (isNaN(n))
                n = Number(root.F["default"]) || 0
            intCtl.value = Math.max(intCtl.from, Math.min(intCtl.to, Math.round(n)))
        } else if (root.isBool) {
            boolCtl.checked = (v === true)
        } else if (root.isEnum) {
            for (var i = 0; i < enumCtl.count; ++i) {
                if (Number(enumCtl.valueAt(i)) === Number(v)) {
                    enumCtl.currentIndex = i
                    break
                }
            }
        }
        root.syncing = false
    }

    Component.onCompleted: {
        if (root.isEnum) {
            var opts = root.f.intOptions !== undefined ? root.f.intOptions : []
            var m = []
            for (var i = 0; i < opts.length; ++i)
                m.push({ value: opts[i][0], text: opts[i][1] })
            enumCtl.model = m
        }
        sync()
    }

    Connections {
        target: bridge
        function onFieldsChanged() { root.sync() }
    }
}
