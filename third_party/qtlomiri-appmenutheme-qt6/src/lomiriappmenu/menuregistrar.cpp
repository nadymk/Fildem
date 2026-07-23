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

#include "menuregistrar.h"
#include "registry.h"
#include "logging.h"

#include <QDebug>
#include <QDBusObjectPath>
#include <QGuiApplication>
#include <qpa/qplatformnativeinterface.h>
#include <qpa/qplatformwindow.h>

namespace {

bool isMirClient() {
    return qGuiApp->platformName() == "ubuntumirclient";
}

}

LomiriMenuRegistrar::LomiriMenuRegistrar()
    : m_connection(nullptr)
    , m_registeredProcessId(~0)
{
    GError *error = NULL;
    m_connection = g_bus_get_sync (G_BUS_TYPE_SESSION, NULL, &error);
    if (!m_connection) {
        qCWarning(lomiriappmenuRegistrar, "Failed to retrieve session bus - %s", error ? error->message : "unknown error");
        g_error_free (error);
        return;
    }
    m_service = g_dbus_connection_get_unique_name(m_connection);
    connect(LomiriMenuRegistry::instance(), &LomiriMenuRegistry::serviceChanged, this, &LomiriMenuRegistrar::onRegistrarServiceChanged);

    if (isMirClient()) {
        auto nativeInterface = qGuiApp->platformNativeInterface();
        connect(nativeInterface, &QPlatformNativeInterface::windowPropertyChanged, this, [this](QPlatformWindow* window, const QString &property) {
            if (property != QStringLiteral("persistentSurfaceId")) {
                return;
            }
            if (window->window() == m_window) {
                registerMenuForWindow(m_window, m_path);
            }
        });
    }
}

LomiriMenuRegistrar::~LomiriMenuRegistrar()
{
    if (m_connection) {
        g_object_unref(m_connection);
    }
    unregisterMenu();
}

void LomiriMenuRegistrar::registerMenuForWindow(QWindow* window, const QDBusObjectPath& path)
{
    unregisterMenu();

    m_window = window;
    m_path = path;

    registerMenu();
}

void LomiriMenuRegistrar::registerMenu()
{
    if (LomiriMenuRegistry::instance()->isConnected() && m_window) {
        if (isMirClient()) {
            registerSurfaceMenu();
        } else {
            registerApplicationMenu();
        }
    }
}

void LomiriMenuRegistrar::unregisterMenu()
{
    if (!m_registeredSurfaceId.isEmpty()) {
        unregisterSurfaceMenu();
    } else if (m_registeredProcessId != ~0) {
        unregisterApplicationMenu();
    }
}

void LomiriMenuRegistrar::registerSurfaceMenu()
{
    auto nativeInterface = qGuiApp->platformNativeInterface();
    QByteArray persistentSurfaceId = nativeInterface->windowProperty(m_window->handle(), "persistentSurfaceId", QByteArray()).toByteArray();
    if (persistentSurfaceId.isEmpty()) return;

    LomiriMenuRegistry::instance()->registerSurfaceMenu(persistentSurfaceId, m_path, m_service);
    m_registeredSurfaceId = persistentSurfaceId;
}

void LomiriMenuRegistrar::unregisterSurfaceMenu()
{
    if (LomiriMenuRegistry::instance()->isConnected()) {
        LomiriMenuRegistry::instance()->unregisterSurfaceMenu(m_registeredSurfaceId, m_path);
    }
    m_registeredSurfaceId.clear();
}

void LomiriMenuRegistrar::registerApplicationMenu()
{
    pid_t pid = getpid();
    LomiriMenuRegistry::instance()->registerApplicationMenu(pid, m_path, m_service);
    m_registeredProcessId = pid;
}

void LomiriMenuRegistrar::unregisterApplicationMenu()
{
    if (LomiriMenuRegistry::instance()->isConnected()) {
        LomiriMenuRegistry::instance()->unregisterApplicationMenu(m_registeredProcessId, m_path);
    }
    m_registeredProcessId = ~0;
}

void LomiriMenuRegistrar::onRegistrarServiceChanged()
{
    unregisterMenu();
    registerMenu();
}
