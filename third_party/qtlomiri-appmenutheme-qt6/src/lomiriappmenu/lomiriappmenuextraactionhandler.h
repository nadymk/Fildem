/*
 * Copyright (C) 2017 Canonical, Ltd.
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

#ifndef LOMIRIAPPMENUEXTRAACTIONHANDLER_H
#define LOMIRIAPPMENUEXTRAACTIONHANDLER_H

#include <gio/gio.h>

class QByteArray;

class LomiriGMenuModelExporter;

class LomiriAppMenuExtraActionHandler
{
public:
    LomiriAppMenuExtraActionHandler();
    ~LomiriAppMenuExtraActionHandler();

    bool connect(GDBusConnection *connection, const QByteArray &menuPath, LomiriGMenuModelExporter *gmenuexporter);
    void disconnect(GDBusConnection *connection);

private:
    GDBusNodeInfo *m_introspection_data;
    guint m_registration_id;
};

#endif
