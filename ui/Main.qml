import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: bridge.initialWidth
    height: bridge.initialHeight
    minimumWidth: 620
    minimumHeight: 440
    visible: true
    title: "sdl-freerdp3 配置 — " + bridge.title + (bridge.dirty ? " •" : "")

    // schema 走 JSON 再 parse 成纯 JS 数组。
    //
    // 两个坑，都实测过：
    //  1. 不要直接传 Python 的 QVariantList<QVariantMap>：QML 对它的暴露方式是
    //     「map 的键作为 role」，嵌套 Repeater 里 modelData 不可靠。
    //  2. 不要写成 `readonly property var schemaModel: JSON.parse(...)` 这种绑定：
    //     绑定会被反复求值，每次都产生**新的数组对象**，导致 grp 变化、内层
    //     Repeater 无限重建 delegate，而旧 delegate 销毁时绑定仍在求值 → 刷屏报错。
    //     所以只在 onCompleted 里赋值一次。
    property var schemaModel: []
    property bool schemaReady: false
    property bool previewOpen: false

    // ===================================================== 主体

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            // ------------------------------------------- 左：连接列表
            Frame {
                SplitView.preferredWidth: 270
                SplitView.minimumWidth: 180
                padding: 8

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    TextField {
                        Layout.fillWidth: true
                        placeholderText: "搜索名称 / 地址…"
                        onTextEdited: bridge.search = text
                    }

                    ListView {
                        id: list
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 1
                        // 桌面应用不要越界回弹（Qt 默认 DragAndOvershootBounds）
                        boundsBehavior: Flickable.StopAtBounds

                        model: ListModel { id: listModel }

                        delegate: ItemDelegate {
                            id: item
                            width: ListView.view.width
                            highlighted: model.isCurrent

                            contentItem: RowLayout {
                                spacing: 6

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Label {
                                        text: model.displayName
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                        font.bold: model.isDraft
                                    }
                                    Label {
                                        text: model.subtitle
                                        visible: text.length > 0
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                        font.pixelSize: 11
                                        opacity: 0.6
                                    }
                                }

                                ToolButton {
                                    text: "✕"
                                    visible: !model.isDraft && (item.hovered || item.highlighted)
                                    onClicked: confirmDelete.ask(model.displayName)
                                }
                            }

                            onClicked: bridge.selectProfile(model.isDraft ? bridge.draftLabel : model.displayName)
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        text: bridge.profileCount
                        opacity: 0.6
                        font.pixelSize: 11
                    }
                }
            }

            // ------------------------------------------- 右：编辑
            ScrollView {
                id: formScroll
                SplitView.fillWidth: true
                // 必须容得下最宽的一行表单：FieldRow 的标签列固定 190px，
                // 再加上控件最小宽度和间距。小于这个值时各行会按各自的最小宽度
                // 撑破面板（不同分组宽度还不一致）。详见 ui/FieldRow.qml。
                SplitView.minimumWidth: 420
                contentWidth: availableWidth
                // ScrollView 自己没有 boundsBehavior，但它的 contentItem 就是内部的
                // Flickable，所以用 Binding 设上去（比 onCompleted 赋值稳，contentItem
                // 换掉时仍然生效）。
                Binding {
                    target: formScroll.contentItem
                    property: "boundsBehavior"
                    value: Flickable.StopAtBounds
                }

                ColumnLayout {
                    width: formScroll.availableWidth - 24
                    x: 12
                    spacing: 10

                    // 名称（GUI 字段，不是 .rdp 键）
                    Frame {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        RowLayout {
                            anchors.fill: parent
                            Label { text: "名称"; Layout.preferredWidth: 190 }
                            Label {
                                Layout.fillWidth: true
                                text: bridge.isDraft
                                      ? "（未保存 — 点击「保存」命名）"
                                      : bridge.title
                                font.bold: !bridge.isDraft
                                opacity: bridge.isDraft ? 0.6 : 1
                                elide: Text.ElideRight
                            }
                        }
                    }

                    // 分组表单
                    //
                    // 注意 `schemaReady` 门闩：schemaModel 是在 window 的
                    // Component.onCompleted 里赋值的，而 Repeater 早于它构建。
                    // 不加门闩的话，内层 Repeater 会在 grp 还没就绪时先建一批
                    // delegate，之后再重建，结果是字段错位 + 一堆空 key 的行。
                    Repeater {
                        model: win.schemaReady ? win.schemaModel : []
                        delegate: Frame {
                            id: groupFrame
                            Layout.fillWidth: true
                            required property var modelData
                            property var grp: modelData
                            property bool expanded: groupFrame.grp.open === true

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 8

                                Label {
                                    Layout.fillWidth: true
                                    text: (groupFrame.expanded ? "▾  " : "▸  ") + groupFrame.grp.title
                                    font.bold: true
                                    TapHandler {
                                        onTapped: groupFrame.expanded = !groupFrame.expanded
                                    }
                                }

                                Repeater {
                                    model: groupFrame.grp.fields
                                    delegate: FieldRow {
                                        Layout.fillWidth: true
                                        visible: groupFrame.expanded
                                        fld: groupFrame.grp.fields[index]
                                    }
                                }
                            }
                        }
                    }

                    // ----------------------------------- .rdp 预览
                    Frame {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 8
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 6

                            Label {
                                Layout.fillWidth: true
                                text: (win.previewOpen ? "▾  " : "▸  ") + ".rdp 预览"
                                font.bold: true
                                TapHandler {
                                    onTapped: win.previewOpen = !win.previewOpen
                                }
                            }

                            ScrollView {
                                id: previewScroll
                                Layout.fillWidth: true
                                Layout.preferredHeight: win.previewOpen ? 220 : 0
                                visible: win.previewOpen
                                clip: true
                                Binding {
                                    target: previewScroll.contentItem
                                    property: "boundsBehavior"
                                    value: Flickable.StopAtBounds
                                }

                                TextArea {
                                    readOnly: true
                                    text: bridge.previewText
                                    font.family: "monospace"
                                    wrapMode: TextArea.NoWrap
                                    selectByMouse: true
                                }
                            }
                        }
                    }
                }
            }
        }

        // ------------------------------------------- 底部按钮条
        Frame {
            Layout.fillWidth: true
            padding: 8

            RowLayout {
                anchors.fill: parent
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: bridge.status
                    elide: Text.ElideRight
                    opacity: 0.7
                }

                Label {
                    text: bridge.binaryHint
                    opacity: 0.45
                    font.pixelSize: 11
                }

                Button {
                    text: "还原"
                    visible: bridge.canRevert
                    onClicked: bridge.revert()
                }
                Button {
                    text: "另存为…"
                    visible: !bridge.isDraft
                    onClicked: saveAsDialog.open()
                }
                Button {
                    text: bridge.isDraft ? "保存…" : "保存"
                    enabled: bridge.dirty || bridge.isDraft
                    onClicked: bridge.isDraft ? saveAsDialog.open() : bridge.save()
                }
                Button {
                    text: "连接"
                    highlighted: true
                    onClicked: bridge.connectNow()
                }
            }
        }
    }

    // ===================================================== 列表填充

    function rebuildList() {
        listModel.clear()
        listModel.append({
            displayName: bridge.draftLabel,
            subtitle: "不保存，直接连接",
            isDraft: true,
            isCurrent: bridge.isDraft
        })
        var ps = bridge.visibleProfiles
        for (var i = 0; i < ps.length; ++i) {
            listModel.append({
                displayName: ps[i].name,
                subtitle: ps[i].subtitle,
                isDraft: false,
                isCurrent: (!bridge.isDraft && bridge.title === ps[i].name)
            })
        }
    }

    Connections {
        target: bridge
        function onProfilesChanged() { win.rebuildList() }
        function onTitleChanged() { win.rebuildList() }
    }

    Component.onCompleted: {
        schemaModel = JSON.parse(bridge.schemaJson)
        schemaReady = true
        rebuildList()
    }

    onClosing: bridge.saveWindowSize(width, height)

    // ===================================================== 对话框

    Dialog {
        id: saveAsDialog
        anchors.centerIn: parent
        modal: true
        title: "保存配置"
        standardButtons: Dialog.Ok | Dialog.Cancel
        width: 400

        ColumnLayout {
            anchors.fill: parent
            spacing: 8
            Label { text: "配置名称（同时作为文件名）" }
            TextField {
                id: nameInput
                Layout.fillWidth: true
                placeholderText: "例如：办公室"
                selectByMouse: true
                onAccepted: saveAsDialog.accept()
            }
        }

        onOpened: {
            nameInput.text = bridge.isDraft ? "" : bridge.title
            nameInput.forceActiveFocus()
        }
        onAccepted: {
            if (nameInput.text.trim().length > 0)
                bridge.saveAs(nameInput.text.trim())
        }
    }

    Dialog {
        id: confirmDelete
        anchors.centerIn: parent
        modal: true
        title: "删除配置"
        property string target: ""
        standardButtons: Dialog.Yes | Dialog.No
        width: 380

        function ask(name) {
            target = name
            open()
        }

        Label {
            anchors.fill: parent
            wrapMode: Text.WordWrap
            text: "把「" + confirmDelete.target + "」移入回收站？\n\n文件不会真正删除，可在\n~/.config/sdl-freerdp3-gui/trash/ 找回。"
        }

        onAccepted: bridge.deleteProfile(target)
    }
}
