/*
 * Copyright (C) 2016 Canonical, Ltd.
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU Lesser General Public License version 3, as published by
 * the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
 * SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef EXPORTEDPLATFORMMENUBAR_H
#define EXPORTEDPLATFORMMENUBAR_H

#include <qpa/qplatformmenu.h>

// Local
class LomiriGMenuModelExporter;
class LomiriMenuRegistrar;
class QWindow;

class LomiriPlatformMenuBar : public QPlatformMenuBar
{
    Q_OBJECT
public:
    LomiriPlatformMenuBar();
    ~LomiriPlatformMenuBar();

    QString exportedPath() const;

    virtual void insertMenu(QPlatformMenu *menu, QPlatformMenu* before) override;
    virtual void removeMenu(QPlatformMenu *menu) override;
    virtual void syncMenu(QPlatformMenu *menu) override;
    virtual void handleReparent(QWindow *newParentWindow) override;
    virtual QPlatformMenu *menuForTag(quintptr tag) const override;

    const QList<QPlatformMenu*> menus() const;

    QDebug operator<<(QDebug stream);

#if QT_VERSION >= QT_VERSION_CHECK(5, 6, 0)
    virtual QPlatformMenu *createMenu() const override;
#endif

Q_SIGNALS:
    void menuInserted(QPlatformMenu *menu);
    void menuRemoved(QPlatformMenu *menu);

    void structureChanged();
    void ready();

private:
    void setReady(bool);

    QList<QPlatformMenu*> m_menus;
    QScopedPointer<LomiriGMenuModelExporter> m_exporter;
    QScopedPointer<LomiriMenuRegistrar> m_registrar;
    bool m_ready;
};

#define MENU_PROPERTY(class, name, type, defaultValue) \
    static type get_##name(const class *menuItem) { return menuItem->m_##name; } \
    type m_##name = defaultValue;

class Q_DECL_EXPORT LomiriPlatformMenu : public QPlatformMenu
{
    Q_OBJECT
public:
    LomiriPlatformMenu();
    ~LomiriPlatformMenu();

    virtual void insertMenuItem(QPlatformMenuItem *menuItem, QPlatformMenuItem *before) override;
    virtual void removeMenuItem(QPlatformMenuItem *menuItem) override;
    virtual void syncMenuItem(QPlatformMenuItem *menuItem) override;
    virtual void syncSeparatorsCollapsible(bool enable) override;

    virtual void setTag(quintptr tag) override;
    virtual quintptr tag() const override;

    virtual void setText(const QString &text) override;
    virtual void setIcon(const QIcon &icon) override;
    virtual void setEnabled(bool isEnabled) override;
    virtual void setVisible(bool isVisible) override;
    virtual void setMinimumWidth(int width) override;
    virtual void setFont(const QFont &font) override;

    virtual void showPopup(const QWindow *parentWindow, const QRect &targetRect, const QPlatformMenuItem *item) override;

    virtual void dismiss() override; // Closes this and all its related menu popups

    virtual QPlatformMenuItem *menuItemAt(int position) const override;
    virtual QPlatformMenuItem *menuItemForTag(quintptr tag) const override;

    virtual QPlatformMenuItem *createMenuItem() const override;
#if QT_VERSION >= QT_VERSION_CHECK(5, 6, 0)
    virtual QPlatformMenu *createSubMenu() const override;
#endif

    int id() const;

    const QList<QPlatformMenuItem*> menuItems() const;

    QDebug operator<<(QDebug stream);

Q_SIGNALS:
    void menuItemInserted(QPlatformMenuItem *menuItem);
    void menuItemRemoved(QPlatformMenuItem *menuItem);
    void structureChanged();
    void enabledChanged(bool);

private:
    MENU_PROPERTY(LomiriPlatformMenu, visible, bool, true)
    MENU_PROPERTY(LomiriPlatformMenu, text, QString, QString())
    MENU_PROPERTY(LomiriPlatformMenu, enabled, bool, true)
    MENU_PROPERTY(LomiriPlatformMenu, icon, QIcon, QIcon())

    quintptr m_tag;
    QList<QPlatformMenuItem*> m_menuItems;
    const QWindow* m_parentWindow;
    QScopedPointer<LomiriGMenuModelExporter> m_exporter;
    QScopedPointer<LomiriMenuRegistrar> m_registrar;

    friend class LomiriGMenuModelExporter;
};


class Q_DECL_EXPORT LomiriPlatformMenuItem : public QPlatformMenuItem
{
    Q_OBJECT
public:
    LomiriPlatformMenuItem();
    ~LomiriPlatformMenuItem();

    virtual void setTag(quintptr tag) override;
    virtual quintptr tag() const override;

    virtual void setText(const QString &text) override;
    virtual void setIcon(const QIcon &icon) override;
    virtual void setMenu(QPlatformMenu *menu) override;
    virtual void setVisible(bool isVisible) override;
    virtual void setIsSeparator(bool isSeparator) override;
    virtual void setFont(const QFont &font) override;
    virtual void setRole(MenuRole role) override;
    virtual void setCheckable(bool checkable) override;
    virtual void setChecked(bool isChecked) override;
    virtual void setShortcut(const QKeySequence& shortcut) override;
    virtual void setEnabled(bool enabled) override;
    virtual void setIconSize(int size) override;

    QPlatformMenu* menu() const;

    QDebug operator<<(QDebug stream);

Q_SIGNALS:
    void checkedChanged(bool);
    void enabledChanged(bool);
    void visibleChanged(bool);

private:
    MENU_PROPERTY(LomiriPlatformMenuItem, separator, bool, false)
    MENU_PROPERTY(LomiriPlatformMenuItem, visible, bool, true)
    MENU_PROPERTY(LomiriPlatformMenuItem, text, QString, QString())
    MENU_PROPERTY(LomiriPlatformMenuItem, enabled, bool, true)
    MENU_PROPERTY(LomiriPlatformMenuItem, checkable, bool, false)
    MENU_PROPERTY(LomiriPlatformMenuItem, checked, bool, false)
    MENU_PROPERTY(LomiriPlatformMenuItem, shortcut, QKeySequence, QKeySequence())
    MENU_PROPERTY(LomiriPlatformMenuItem, icon, QIcon, QIcon())
    MENU_PROPERTY(LomiriPlatformMenuItem, iconSize, int, 16)
    MENU_PROPERTY(LomiriPlatformMenuItem, menu, QPlatformMenu*, nullptr)


    quintptr m_tag;
    friend class LomiriGMenuModelExporter;
};

#endif // EXPORTEDPLATFORMMENUBAR_H
