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

#ifndef GMENUMODELEXPORTER_H
#define GMENUMODELEXPORTER_H

#include "gmenumodelplatformmenu.h"

#include <gio/gio.h>

#include <QTimer>
#include <QMap>
#include <QSet>
#include <QMetaObject>

class LomiriAppMenuExtraActionHandler;

// Base class for a gmenumodel exporter
class LomiriGMenuModelExporter : public QObject
{
    Q_OBJECT
public:
    virtual ~LomiriGMenuModelExporter();

    void exportModels();
    void unexportModels();

    QString menuPath() const { return m_menuPath;}

    void aboutToShow(quint64 tag);

protected:
    LomiriGMenuModelExporter(QObject *parent);

    GMenuItem *createSubmenu(QPlatformMenu* platformMenu, LomiriPlatformMenuItem* forItem);
    GMenuItem *createMenuItem(QPlatformMenuItem* platformMenuItem, GMenu *parentMenu);
    GMenuItem *createSection(QList<QPlatformMenuItem*>::const_iterator iter, QList<QPlatformMenuItem*>::const_iterator end);
    void addAction(const QByteArray& name, LomiriPlatformMenuItem* gplatformItem, GMenu *parentMenu);

    void addSubmenuItems(LomiriPlatformMenu* gplatformMenu, GMenu* menu);
    void processItemForGMenu(QPlatformMenuItem* item, GMenu* gmenu);

    void clear();

    void timerEvent(QTimerEvent *e) override;

protected:
    GDBusConnection *m_connection;
    GMenu *m_gmainMenu;
    GSimpleActionGroup *m_gactionGroup;
    guint m_exportedModel;
    guint m_exportedActions;
    LomiriAppMenuExtraActionHandler *m_lomiriAppMenuExtraHandler;
    QTimer m_structureTimer;
    QString m_menuPath;

    // LomiriPlatformMenu::tag -> LomiriPlatformMenu
    QMap<quint64, LomiriPlatformMenu*> m_submenusWithTag;

    // LomiriPlatformMenu -> reload TimerId (startTimer)
    QHash<LomiriPlatformMenu*, int> m_reloadMenuTimers;

    QHash<LomiriPlatformMenu*, GMenu*> m_gmenusForMenus;

    QHash<GMenu*, QSet<QByteArray>> m_actions;
    QHash<GMenu*, QVector<QMetaObject::Connection>> m_propertyConnections;

};

// Class which exports a qt platform menu bar.
class LomiriMenuBarExporter : public LomiriGMenuModelExporter
{
public:
    LomiriMenuBarExporter(LomiriPlatformMenuBar *parent);
    ~LomiriMenuBarExporter();
};

// Class which exports a qt platform menu.
// This will allow exporting of context menus.
class LomiriMenuExporter : public LomiriGMenuModelExporter
{
public:
    LomiriMenuExporter(LomiriPlatformMenu *parent);
    ~LomiriMenuExporter();
};

#endif // GMENUMODELEXPORTER_H
