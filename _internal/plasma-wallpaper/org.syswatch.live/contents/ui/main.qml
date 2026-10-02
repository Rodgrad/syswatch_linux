import QtQuick
import QtCore
import org.kde.plasma.plasmoid

WallpaperItem {
    id: root
    property string imagePath: StandardPaths.writableLocation(StandardPaths.GenericCacheLocation).toString() + "/syswatch/wallpaper.png"
    Rectangle {
        anchors.fill: parent
        color: "#07131e"
        Image {
            id: dashboard
            anchors.fill: parent
            anchors.margins: 0
            fillMode: Image.PreserveAspectFit
            cache: false
            smooth: true
            source: root.imagePath
        }
        Text {
            anchors.centerIn: parent
            visible: dashboard.status !== Image.Ready
            color: "#25e5ef"
            text: "Start SysWatch with: python main.py --wallpaper"
        }
    }
    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: {
            dashboard.source = ""
            dashboard.source = root.imagePath
        }
    }
}
