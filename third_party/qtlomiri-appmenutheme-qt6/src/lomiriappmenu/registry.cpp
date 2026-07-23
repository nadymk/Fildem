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

#include "registry.h"
#include "logging.h"
#include "menuregistrar_interface.h"

#include <QDBusObjectPath>
#include <QDBusServiceWatcher>

Q_LOGGING_CATEGORY(lomiriappmenuRegistrar, "lomiriappmenu.registrar", QtWarningMsg)

#define REGISTRAR_SERVICE "com.lomiri.MenuRegistrar"
#define REGISTRY_OBJECT_PATH "/com/lomiri/MenuRegistrar"

LomiriMenuRegistry *LomiriMenuRegistry::instance()
{
    static LomiriMenuRegistry* registry(new LomiriMenuRegistry());
    return registry;
}

LomiriMenuRegistry::LomiriMenuRegistry(QObject* parent)
    : QObject(parent)
    , m_serviceWatcher(new QDBusServiceWatcher(REGISTRAR_SERVICE, QDBusConnection::sessionBus(), QDBusServiceWatcher::WatchForOwnerChange, this))
    , m_interface(new ComLomiriMenuRegistrarInterface(REGISTRAR_SERVICE, REGISTRY_OBJECT_PATH, QDBusConnection::sessionBus(), this))
    , m_connected(m_interface->isValid())
{
    connect(m_serviceWatcher.data(), &QDBusServiceWatcher::serviceOwnerChanged, this, &LomiriMenuRegistry::serviceOwnerChanged);
}

LomiriMenuRegistry::~LomiriMenuRegistry()
{
}

void LomiriMenuRegistry::registerApplicationMenu(pid_t pid, QDBusObjectPath menuObjectPath, const QString &service)
{
    qCDebug(lomiriappmenuRegistrar, "LomiriMenuRegistry::registerMenu(pid=%d, menuObjectPath=%s, service=%s)",
            pid,
            qPrintable(menuObjectPath.path()),
            qPrintable(service));

    m_interface->RegisterAppMenu(pid, menuObjectPath, menuObjectPath, service);
}

void LomiriMenuRegistry::unregisterApplicationMenu(pid_t pid, QDBusObjectPath menuObjectPath)
{
    qCDebug(lomiriappmenuRegistrar, "LomiriMenuRegistry::unregisterSurfaceMenu(pid=%d, menuObjectPath=%s)",
            pid,
            qPrintable(menuObjectPath.path()));

    m_interface->UnregisterAppMenu(pid, menuObjectPath);
}

void LomiriMenuRegistry::registerSurfaceMenu(const QString &surfaceId, QDBusObjectPath menuObjectPath, const QString &service)
{
    qCDebug(lomiriappmenuRegistrar, "LomiriMenuRegistry::registerMenu(surfaceId=%s, menuObjectPath=%s, service=%s)",
            qPrintable(surfaceId),
            qPrintable(menuObjectPath.path()),
            qPrintable(service));

    m_interface->RegisterSurfaceMenu(surfaceId, menuObjectPath, menuObjectPath, service);
}

void LomiriMenuRegistry::unregisterSurfaceMenu(const QString &surfaceId, QDBusObjectPath menuObjectPath)
{
    qCDebug(lomiriappmenuRegistrar, "LomiriMenuRegistry::unregisterSurfaceMenu(surfaceId=%s, menuObjectPath=%s)",
            qPrintable(surfaceId),
            qPrintable(menuObjectPath.path()));

    m_interface->UnregisterSurfaceMenu(surfaceId, menuObjectPath);
}


void LomiriMenuRegistry::serviceOwnerChanged(const QString &serviceName, const QString& oldOwner, const QString &newOwner)
{
    qCDebug(lomiriappmenuRegistrar, "LomiriMenuRegistry::serviceOwnerChanged(newOwner=%s)", qPrintable(newOwner));

    if (serviceName != REGISTRAR_SERVICE) return;

    if (oldOwner != newOwner) {
        m_connected = !newOwner.isEmpty();
        Q_EMIT serviceChanged();
    }
}
