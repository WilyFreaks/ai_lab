/**
 * Load persisted scenario controls from local/ai_lab_scenarios.conf via
 * | scenariocontrol action=status scenario="<name>"
 * when the Scenario dropdown changes and once on dashboard load.
 */
require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/mvc/searchmanager",
    "splunkjs/mvc/simplexml/ready!"
], function($, mvc, SearchManager) {
    "use strict";

    var logPrefix = "[scenario_control_status]";

    function safeGetComponent(id, create) {
        try {
            if (mvc && mvc.Components && typeof mvc.Components.get === "function") {
                var c = mvc.Components.get(id);
                if (c) {
                    return c;
                }
            }
            if (create && mvc && mvc.Components && typeof mvc.Components.getInstance === "function") {
                return mvc.Components.getInstance(id, { create: true });
            }
        } catch (e) {
            console.warn(logPrefix, "safeGetComponent failed", id, e);
        }
        return null;
    }

    var defaultTokenModelun = safeGetComponent("default", true);
    var submittedTokenModelun = safeGetComponent("submitted", true);

    function scenarioToken() {
        if (!defaultTokenModelun || typeof defaultTokenModelun.get !== "function") {
            return "scenario_1";
        }
        var v =
            defaultTokenModelun.get("form.scenario") ||
            defaultTokenModelun.get("scenario");
        return (v == null || v === "") ? "scenario_1" : String(v);
    }

    function fieldNames(fields) {
        if (!fields || !fields.length) {
            return [];
        }
        return fields.map(function(f) {
            return typeof f === "string" ? f : f && f.name ? f.name : "";
        });
    }

    function packToRow(pack) {
        if (!pack) {
            return null;
        }
        if (Array.isArray(pack)) {
            return pack.length ? pack[0] : null;
        }
        var rows = pack.rows;
        var fields = pack.fields;
        if (!rows || !rows.length) {
            return null;
        }
        var names = fieldNames(fields);
        var row = rows[0];
        if (row && typeof row === "object" && !Array.isArray(row)) {
            return row;
        }
        if (!names.length || !Array.isArray(row)) {
            return null;
        }
        var obj = {};
        names.forEach(function(name, i) {
            if (name) {
                obj[name] = row[i];
            }
        });
        return obj;
    }

    function applyRow(row) {
        if (!row) {
            return;
        }
        var act = row.active == null ? "0" : String(row.active);
        var fs = row.fault_start == null ? "0" : String(row.fault_start);
        var fd = row.fault_duration == null ? "0" : String(row.fault_duration);

        if (defaultTokenModelun && typeof defaultTokenModelun.set === "function") {
            defaultTokenModelun.set("form.active", act);
            defaultTokenModelun.set("form.fault_start", fs);
            defaultTokenModelun.set("form.fault_duration", fd);
        }
        if (submittedTokenModelun && typeof submittedTokenModelun.set === "function") {
            submittedTokenModelun.set("form.active", act);
            submittedTokenModelun.set("form.fault_start", fs);
            submittedTokenModelun.set("form.fault_duration", fd);
        }

        console.log(logPrefix, "synced form from config", {
            active: act,
            fault_start: fs,
            fault_duration: fd,
            activated: row.activated
        });
    }

    var statusSearch = safeGetComponent("scenario_status_dm", false);
    if (!statusSearch) {
        try {
            statusSearch = new SearchManager({
                id: "scenario_status_dm",
                preview: false,
                cache: false,
                autostart: false,
                search: '| scenariocontrol action=status scenario="scenario_1"'
            });
        } catch (e) {
            console.warn(logPrefix, "failed to create SearchManager", e);
            statusSearch = null;
        }
    }

    function runStatusSearch() {
        if (!statusSearch || typeof statusSearch.set !== "function") {
            console.warn(logPrefix, "status search unavailable");
            return;
        }
        var sc = scenarioToken().replace(/"/g, "");
        try {
            statusSearch.set(
                "search",
                '| scenariocontrol action=status scenario="' + sc + '"'
            );
        } catch (e) {
            console.warn(logPrefix, "failed to set search", e);
            return;
        }

        var results = null;
        try {
            results = statusSearch.data("results", { count: 50, offset: 0 });
        } catch (e) {
            console.warn(logPrefix, "failed to create results model", e);
            return;
        }
        if (!results) {
            console.warn(logPrefix, "results model unavailable");
            return;
        }

        function finish() {
            if (!results.hasData()) {
                console.log(logPrefix, "status: no data");
                return;
            }
            var row = packToRow(results.data());
            if (!row || String(row.status || "") !== "ok") {
                console.warn(logPrefix, "status: bad row", row);
                return;
            }
            applyRow(row);
        }

        if (typeof results.off === "function") {
            results.off("data");
        }
        if (typeof results.once === "function") {
            results.once("data", finish);
        }
        if (typeof statusSearch.off === "function") {
            statusSearch.off("search:error");
        }
        if (typeof statusSearch.once === "function") {
            statusSearch.once("search:error", function(err) {
                console.warn(logPrefix, "search:error", err);
            });
        }
        if (typeof statusSearch.startSearch === "function") {
            statusSearch.startSearch();
        }
    }

    if (defaultTokenModelun && typeof defaultTokenModelun.on === "function") {
        defaultTokenModelun.on("change:form.scenario", function() {
            runStatusSearch();
        });
    }

    $(document).ready(function() {
        setTimeout(function() {
            try {
                runStatusSearch();
            } catch (e) {
                console.warn(logPrefix, "initial run failed", e);
            }
        }, 150);
    });
});
