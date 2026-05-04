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
    var defaultTokenModelun = mvc.Components.getInstance("default", { create: true });
    var submittedTokenModelun = mvc.Components.getInstance("submitted", { create: true });

    function scenarioToken() {
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

        defaultTokenModelun.set("form.active", act);
        defaultTokenModelun.set("form.fault_start", fs);
        defaultTokenModelun.set("form.fault_duration", fd);
        submittedTokenModelun.set("form.active", act);
        submittedTokenModelun.set("form.fault_start", fs);
        submittedTokenModelun.set("form.fault_duration", fd);

        console.log(logPrefix, "synced form from config", {
            active: act,
            fault_start: fs,
            fault_duration: fd,
            activated: row.activated
        });
    }

    var statusSearch = new SearchManager({
        id: "scenario_status_dm",
        preview: false,
        cache: false,
        autostart: false,
        search: '| scenariocontrol action=status scenario="scenario_1"'
    });

    function runStatusSearch() {
        var sc = scenarioToken().replace(/"/g, "");
        statusSearch.set(
            "search",
            '| scenariocontrol action=status scenario="' + sc + '"'
        );

        var results = statusSearch.data("results", { count: 50, offset: 0 });

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

        results.off("data");
        results.once("data", finish);
        statusSearch.off("search:error");
        statusSearch.once("search:error", function(err) {
            console.warn(logPrefix, "search:error", err);
        });
        statusSearch.startSearch();
    }

    defaultTokenModelun.on("change:form.scenario", function() {
        runStatusSearch();
    });

    mvc.utils.onEachReady(function() {
        setTimeout(function() {
            runStatusSearch();
        }, 150);
    });
});
