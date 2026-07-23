TARGET = lomiriappmenu
TEMPLATE = lib

QT -= gui
QT += core-private gui-private dbus
lessThan(QT_MAJOR_VERSION, 6): QT += theme_support-private

CONFIG += plugin no_keywords c++17

# CONFIG += c++11 # only enables C++0x
QMAKE_CXXFLAGS += -fvisibility=hidden -fvisibility-inlines-hidden -Wall
QMAKE_LFLAGS += -Wl,-no-undefined

CONFIG += link_pkgconfig
PKGCONFIG += gio-2.0

DBUS_INTERFACES += com.lomiri.MenuRegistrar.xml

HEADERS += \
    theme.h \
    gmenumodelexporter.h \
    gmenumodelplatformmenu.h \
    logging.h \
    menuregistrar.h \
    registry.h \
    themeplugin.h \
    lomiriappmenuextraactionhandler.h \
    ../shared/lomiritheme.h

SOURCES += \
    theme.cpp \
    gmenumodelexporter.cpp \
    gmenumodelplatformmenu.cpp \
    menuregistrar.cpp \
    registry.cpp \
    themeplugin.cpp \
    lomiriappmenuextraactionhandler.cpp

OTHER_FILES += \
    lomiriappmenu.json

# Installation path
target.path +=  $$[QT_INSTALL_PLUGINS]/platformthemes

INSTALLS += target
