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

// Local
#include "gmenumodelplatformmenu.h"
#include "gmenumodelexporter.h"
#include "registry.h"
#include "menuregistrar.h"
#include "logging.h"

// Qt
#include <QDebug>
#include <QWindow>
#include <QCoreApplication>

#define BAR_DEBUG_MSG qCDebug(lomiriappmenu).nospace() << "LomiriPlatformMenuBar[" << (void*)this <<"]::" << __func__
#define MENU_DEBUG_MSG qCDebug(lomiriappmenu).nospace() << "LomiriPlatformMenu[" << (void*)this <<"]::" << __func__
#define ITEM_DEBUG_MSG qCDebug(lomiriappmenu).nospace() << "LomiriPlatformMenuItem[" << (void*)this <<"]::" << __func__

namespace {

int logRecusion = 0;

}

QDebug operator<<(QDebug stream, LomiriPlatformMenuBar* bar) {
    if (bar) return bar->operator<<(stream);
    return stream;
}
QDebug operator<<(QDebug stream, LomiriPlatformMenu* menu) {
    if (menu) return menu->operator<<(stream);
    return stream;
}
QDebug operator<<(QDebug stream, LomiriPlatformMenuItem* menuItem) {
    if (menuItem) return menuItem->operator<<(stream);
    return stream;
}

LomiriPlatformMenuBar::LomiriPlatformMenuBar()
    : m_exporter(new LomiriMenuBarExporter(this))
    , m_registrar(new LomiriMenuRegistrar())
    , m_ready(false)
{
    BAR_DEBUG_MSG << "()";

    connect(this, &LomiriPlatformMenuBar::menuInserted, this, &LomiriPlatformMenuBar::structureChanged);
    connect(this,&LomiriPlatformMenuBar::menuRemoved, this, &LomiriPlatformMenuBar::structureChanged);
}

LomiriPlatformMenuBar::~LomiriPlatformMenuBar()
{
    BAR_DEBUG_MSG << "()";
}

void LomiriPlatformMenuBar::insertMenu(QPlatformMenu *menu, QPlatformMenu *before)
{
    BAR_DEBUG_MSG << "(menu=" << menu << ", before=" <<  before << ")";

    if (m_menus.contains(menu)) return;

    if (!before) {
        m_menus.push_back(menu);
    } else {
        for (auto iter = m_menus.begin(); iter != m_menus.end(); ++iter) {
            if (*iter == before) {
                m_menus.insert(iter, menu);
                break;
            }
        }
    }
    Q_EMIT menuInserted(menu);
}

void LomiriPlatformMenuBar::removeMenu(QPlatformMenu *menu)
{
    BAR_DEBUG_MSG << "(menu=" << menu << ")";

    QMutableListIterator<QPlatformMenu*> iterator(m_menus);
    while(iterator.hasNext()) {
        if (iterator.next() == menu) {
            iterator.remove();
            break;
        }
    }
    Q_EMIT menuRemoved(menu);
}

void LomiriPlatformMenuBar::syncMenu(QPlatformMenu *menu)
{
    BAR_DEBUG_MSG << "(menu=" << menu << ")";

    Q_UNUSED(menu)
}

void LomiriPlatformMenuBar::handleReparent(QWindow *parentWindow)
{
    BAR_DEBUG_MSG << "(parentWindow=" << parentWindow << ")";

    setReady(true);
    m_registrar->registerMenuForWindow(parentWindow, QDBusObjectPath(m_exporter->menuPath()));
}

QPlatformMenu *LomiriPlatformMenuBar::menuForTag(quintptr tag) const
{
    Q_FOREACH(QPlatformMenu* menu, m_menus) {
        if (menu->tag() == tag) {
            return menu;
        }
    }
    return nullptr;
}

const QList<QPlatformMenu *> LomiriPlatformMenuBar::menus() const
{
    return m_menus;
}

QDebug LomiriPlatformMenuBar::operator<<(QDebug stream)
{
    stream.nospace().noquote() << QString("%1").arg("", logRecusion, QLatin1Char('\t'))
            << "LomiriPlatformMenuBar(this=" << (void*)this << ")" << Qt::endl;
    Q_FOREACH(QPlatformMenu* menu, m_menus) {
        auto myMenu = static_cast<LomiriPlatformMenu*>(menu);
        if (myMenu) {
            logRecusion++;
            stream << myMenu;
            logRecusion--;
        }
    }

    return stream;
}

#if QT_VERSION >= QT_VERSION_CHECK(5, 6, 0)
QPlatformMenu *LomiriPlatformMenuBar::createMenu() const
{
    return new LomiriPlatformMenu();
}
#endif

void LomiriPlatformMenuBar::setReady(bool isReady)
{
    if (m_ready != isReady) {
        m_ready = isReady;
        Q_EMIT ready();
    }
}

//////////////////////////////////////////////////////////////

LomiriPlatformMenu::LomiriPlatformMenu()
    : m_tag(reinterpret_cast<quintptr>(this))
    , m_parentWindow(nullptr)
    , m_exporter(nullptr)
    , m_registrar(nullptr)
{
    MENU_DEBUG_MSG << "()";

    connect(this, &LomiriPlatformMenu::menuItemInserted, this, &LomiriPlatformMenu::structureChanged);
    connect(this, &LomiriPlatformMenu::menuItemRemoved, this, &LomiriPlatformMenu::structureChanged);
}

LomiriPlatformMenu::~LomiriPlatformMenu()
{
    MENU_DEBUG_MSG << "()";
}

void LomiriPlatformMenu::insertMenuItem(QPlatformMenuItem *menuItem, QPlatformMenuItem *before)
{
    MENU_DEBUG_MSG << "(menuItem=" << menuItem << ", before=" << before << ")";

    if (m_menuItems.contains(menuItem)) return;

    if (!before) {
        m_menuItems.push_back(menuItem);
    } else {
        for (auto iter = m_menuItems.begin(); iter != m_menuItems.end(); ++iter) {
            if (*iter == before) {
                m_menuItems.insert(iter, menuItem);
                break;
            }
        }
    }

    Q_EMIT menuItemInserted(menuItem);
}

void LomiriPlatformMenu::removeMenuItem(QPlatformMenuItem *menuItem)
{
    MENU_DEBUG_MSG << "(menuItem=" << menuItem << ")";

    QMutableListIterator<QPlatformMenuItem*> iterator(m_menuItems);
    while(iterator.hasNext()) {
        if (iterator.next() == menuItem) {
            iterator.remove();
            break;
        }
    }
    Q_EMIT menuItemRemoved(menuItem);
}

void LomiriPlatformMenu::syncMenuItem(QPlatformMenuItem *menuItem)
{
    MENU_DEBUG_MSG << "(menuItem=" << menuItem << ")";

    Q_UNUSED(menuItem)
}

void LomiriPlatformMenu::syncSeparatorsCollapsible(bool enable)
{
    MENU_DEBUG_MSG << "(enable=" << enable << ")";
    Q_UNUSED(enable)
}

void LomiriPlatformMenu::setTag(quintptr tag)
{
    MENU_DEBUG_MSG << "(tag=" << tag << ")";
    m_tag = tag;
}

quintptr LomiriPlatformMenu::tag() const
{
    return m_tag;
}

void LomiriPlatformMenu::setText(const QString &text)
{
    MENU_DEBUG_MSG << "(text=" << text << ")";
    if (m_text != text) {
        m_text = text;
    }
}

void LomiriPlatformMenu::setIcon(const QIcon &icon)
{
    MENU_DEBUG_MSG << "(icon=" << icon.name() << ")";

    if (!icon.isNull() || (!m_icon.isNull() && icon.isNull())) {
        m_icon = icon;
    }
}

void LomiriPlatformMenu::setEnabled(bool enabled)
{
    MENU_DEBUG_MSG << "(enabled=" << enabled << ")";

    if (m_enabled != enabled) {
        m_enabled = enabled;
        Q_EMIT enabledChanged(enabled);
    }
}

void LomiriPlatformMenu::setVisible(bool isVisible)
{
    MENU_DEBUG_MSG << "(visible=" << isVisible << ")";

    if (m_visible != isVisible) {
        m_visible = isVisible;
    }
}

void LomiriPlatformMenu::setMinimumWidth(int width)
{
    MENU_DEBUG_MSG << "(width=" << width << ")";

    Q_UNUSED(width)
}

void LomiriPlatformMenu::setFont(const QFont &font)
{
    MENU_DEBUG_MSG << "(font=" << font << ")";

    Q_UNUSED(font)
}

void LomiriPlatformMenu::showPopup(const QWindow *parentWindow, const QRect &targetRect, const QPlatformMenuItem *item)
{
    MENU_DEBUG_MSG << "(parentWindow=" << parentWindow << ", targetRect=" << targetRect << ", item=" << item << ")";

    if (!m_exporter) {
        m_exporter.reset(new LomiriMenuExporter(this));
        m_exporter->exportModels();
    }

    if (parentWindow != m_parentWindow) {
        if (m_parentWindow) {
            m_registrar->unregisterMenu();
        }

        m_parentWindow = parentWindow;

        if (m_parentWindow) {
            if (!m_registrar) m_registrar.reset(new LomiriMenuRegistrar);
            m_registrar->registerMenuForWindow(const_cast<QWindow*>(m_parentWindow),
                                                      QDBusObjectPath(m_exporter->menuPath()));
        }
    }

    Q_UNUSED(targetRect);
    Q_UNUSED(item);
    setVisible(true);
}

void LomiriPlatformMenu::dismiss()
{
    MENU_DEBUG_MSG << "()";

    if (m_registrar) { m_registrar->unregisterMenu(); }
    if (m_exporter) { m_exporter->unexportModels(); }
}

QPlatformMenuItem *LomiriPlatformMenu::menuItemAt(int position) const
{
    if (position < 0 || position >= m_menuItems.count()) return nullptr;
    return m_menuItems.at(position);
}

QPlatformMenuItem *LomiriPlatformMenu::menuItemForTag(quintptr tag) const
{
    Q_FOREACH(QPlatformMenuItem* menuItem, m_menuItems) {
        if (menuItem->tag() == tag) {
            return menuItem;
        }
    }
    return nullptr;
}

QPlatformMenuItem *LomiriPlatformMenu::createMenuItem() const
{
    return new LomiriPlatformMenuItem();
}

#if QT_VERSION >= QT_VERSION_CHECK(5, 6, 0)
QPlatformMenu *LomiriPlatformMenu::createSubMenu() const
{
    return new LomiriPlatformMenu();
}
#endif

const QList<QPlatformMenuItem *> LomiriPlatformMenu::menuItems() const
{
    return m_menuItems;
}

QDebug LomiriPlatformMenu::operator<<(QDebug stream)
{
    stream.nospace().noquote() << QString("%1").arg("", logRecusion, QLatin1Char('\t'))
            << "LomiriPlatformMenu(this=" << (void*)this << ", text=\"" << m_text << "\")" << Qt::endl;
    Q_FOREACH(QPlatformMenuItem* item, m_menuItems) {
        logRecusion++;
        auto myItem = static_cast<LomiriPlatformMenuItem*>(item);
        if (myItem) {
            stream << myItem;
        }
        logRecusion--;
    }
    return stream;
}

//////////////////////////////////////////////////////////////

LomiriPlatformMenuItem::LomiriPlatformMenuItem()
    : m_menu(nullptr)
    , m_tag(reinterpret_cast<quintptr>(this))
{
    ITEM_DEBUG_MSG << "()";
}

LomiriPlatformMenuItem::~LomiriPlatformMenuItem()
{
    ITEM_DEBUG_MSG << "()";
}

void LomiriPlatformMenuItem::setTag(quintptr tag)
{
    ITEM_DEBUG_MSG << "(tag=" << tag << ")";
    m_tag = tag;
}

quintptr LomiriPlatformMenuItem::tag() const
{
    return m_tag;
}

void LomiriPlatformMenuItem::setText(const QString &text)
{
    ITEM_DEBUG_MSG << "(text=" << text << ")";
    if (m_text != text) {
        m_text = text;
    }
}

void LomiriPlatformMenuItem::setIcon(const QIcon &icon)
{
    ITEM_DEBUG_MSG << "(icon=" << icon.name() << ")";

    if (!icon.isNull() || (!m_icon.isNull() && icon.isNull())) {
        m_icon = icon;
    }
}

void LomiriPlatformMenuItem::setVisible(bool isVisible)
{
    ITEM_DEBUG_MSG << "(visible=" << isVisible << ")";
    if (m_visible != isVisible) {
        m_visible = isVisible;
        Q_EMIT visibleChanged(m_visible);
    }
}

void LomiriPlatformMenuItem::setIsSeparator(bool isSeparator)
{
    ITEM_DEBUG_MSG << "(separator=" << isSeparator << ")";
    if (m_separator != isSeparator) {
        m_separator = isSeparator;
    }
}

void LomiriPlatformMenuItem::setFont(const QFont &font)
{
    ITEM_DEBUG_MSG << "(font=" << font << ")";
    Q_UNUSED(font);
}

void LomiriPlatformMenuItem::setRole(QPlatformMenuItem::MenuRole role)
{
    ITEM_DEBUG_MSG << "(role=" << role << ")";
    Q_UNUSED(role);
}

void LomiriPlatformMenuItem::setCheckable(bool checkable)
{
    ITEM_DEBUG_MSG << "(checkable=" << checkable << ")";
    if (m_checkable != checkable) {
        m_checkable = checkable;
    }
}

void LomiriPlatformMenuItem::setChecked(bool isChecked)
{
    ITEM_DEBUG_MSG << "(checked=" << isChecked << ")";
    if (m_checked != isChecked) {
        m_checked = isChecked;
        Q_EMIT checkedChanged(isChecked);
    }
}

void LomiriPlatformMenuItem::setShortcut(const QKeySequence &shortcut)
{
    ITEM_DEBUG_MSG << "(shortcut=" << shortcut << ")";
    if (m_shortcut != shortcut) {
        m_shortcut = shortcut;
    }
}

void LomiriPlatformMenuItem::setEnabled(bool enabled)
{
    ITEM_DEBUG_MSG << "(enabled=" << enabled << ")";
    if (m_enabled != enabled) {
        m_enabled = enabled;
        Q_EMIT enabledChanged(enabled);
    }
}

void LomiriPlatformMenuItem::setIconSize(int size)
{
    ITEM_DEBUG_MSG << "(size=" << size << ")";
    Q_UNUSED(size);
}

void LomiriPlatformMenuItem::setMenu(QPlatformMenu *menu)
{
    ITEM_DEBUG_MSG << "(menu=" << menu << ")";
    if (m_menu != menu) {
        m_menu = menu;

        if (menu) {
            connect(menu, &QObject::destroyed,
                    this, [this] { setMenu(nullptr); });
        }
    }
}

QPlatformMenu *LomiriPlatformMenuItem::menu() const
{
    return m_menu;
}

QDebug LomiriPlatformMenuItem::operator<<(QDebug stream)
{
    QString properties = "text=\"" + m_text + "\"";

    stream.nospace().noquote() << QString("%1").arg("", logRecusion, QLatin1Char('\t'))
            << "LomiriPlatformMenuItem(this=" << (void*)this << ", "
            << (m_separator ? "Separator" : properties) << ")" << Qt::endl;
    if (m_menu) {
        auto myMenu = static_cast<LomiriPlatformMenu*>(m_menu);
        if (myMenu) {
            logRecusion++;
            stream << myMenu;
            logRecusion--;
        }
    }
    return stream;
}
