require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/mvc/searchmanager",
    "splunkjs/mvc/simplexml/ready!"
], function(
    $,
    mvc,
    SearchManager
) {
    "use strict";

    var logPrefix = "[wist]";
    console.log(logPrefix, "module factory running (simplexml/ready)");

    // Global events
    $(document).ready(function() {
        console.log(logPrefix, "DOM is ready");
        applyVisibilityFromReady();
    });
    $(window).on("load", function() {
        console.log(logPrefix, "page load completed");
    });
 
    // Tokens
    var tokens = typeof mvc.Components.get === "function" ? mvc.Components.get("default") : null;
    var submittedTokens = typeof mvc.Components.get === "function" ? mvc.Components.get("submitted") : null;
    var defaultTokenModelun = mvc.Components.getInstance('default', { create: true });
    var submittedTokenModelun = mvc.Components.getInstance('submitted', { create: true });
    function setToken(name, value) {
        defaultTokenModelun.set(name, value);
        submittedTokenModelun.set(name, value);
    }
    function unsetToken(name) {
        defaultTokenModelun.unset(name);
        submittedTokenModelun.unset(name);
    }    
    console.log(logPrefix, "init", "tokens are initialized get(default):", !!tokens, "get(submitted):", !!submittedTokens);

    /* Hide the UI to avoid slideshow symptom */
    setControlHidden(true);
    
    submittedTokenModelun.on("change:status_region_ready", applyVisibilityFromReady);
    defaultTokenModelun.on("change:status_region_ready", applyVisibilityFromReady);
    defaultTokenModelun.on("change:form.region", function() {
        var r = defaultTokenModelun.get("form.region");
        if (r) setToken("status_region", r);
    });
    
    // Search Manager
    var regionSearch = new SearchManager({
        id: "region_search",
        preview: false,
        cache: false,
        autostart: false,
        search: "| workshopregion action=\"status\""
    });

    /* Execute the custom command to retrieve the region settings */
    runRegionSearch(function(row) {
        console.log(logPrefix, "runRegionSearch callback", row);
        if (row) {
            syncFromRow(row);
        }
        applyVisibilityFromReady();
    });

    function fieldNames(fields) {
        if (!fields || !fields.length) {
            console.log(logPrefix, "fieldNames", "(empty)");
            return [];
        }
        var out = fields.map(function(f) {
            if (typeof f === "string") {
                return f;
            }
            return f && f.name ? f.name : "";
        });
        console.log(logPrefix, "fieldNames", out);
        return out;
    }

    function syncFromRow(row) {
        if (!row) {
            console.log(logPrefix, "syncFromRow", "(null row)");
            return;
        }
        console.log(logPrefix, "syncFromRow", row);
        var region = row.region == null ? "" : String(row.region);

        // Set lock/unlock BEFORE status_region_ready so change:status_region_ready listeners do not
        // run applyVisibility while $region_unlocked$ is still unset (dropdown depends on it).
        var ready = String(row.region_ready || "").toLowerCase();
        console.log(logPrefix, "syncFromRow.region_ready -> lock branch", ready);

        // Set status_region BEFORE region_locked so the locked panel's search has its token
        // ready the moment the panel becomes visible (avoids "waiting for input" on reload).
        setToken("region", region);
        setToken("status_region", region);

        if (ready === "true") {
            setToken("region_locked", "true");
            unsetToken("region_unlocked");
            // autoRun=false blocks all panel searches until Submit is clicked.
            // On reload the Submit button is never clicked, so trigger it programmatically.
            setTimeout(function() {
                $(".fieldset button.btn.btn-primary").trigger("click");
            }, 100);
        } else {
            unsetToken("region_locked");
            setToken("region_unlocked", "true");
        }
        setToken("status_region_ready", row.region_ready);
        setToken("status_enabled", row.baseline_generation_enabled);
        setToken("status_backfill_start", row.backfill_start_time == null ? "" : String(row.backfill_start_time));
        if (row.backfill_completed !== undefined) {
            setToken("status_backfill_completed", row.backfill_completed);
        }
    }

    /** Hide fieldset + submit strip until we know region_ready (reduces load flicker). */
    function setControlHidden(hidden) {
        console.log(logPrefix, "setControlHidden", hidden);
        var d = hidden ? "none" : "block";
        var b = hidden ? "none" : "inline-block";
        var $submit = $(".fieldset button.btn.btn-primary");
        console.log(logPrefix, "setControlHidden.targets", { submitCount: $submit.length });
        $submit.css("display", b);
        $("a.hide-global-filters").css("display", hidden ? "none" : "inline");
        $("a.hide-global-filters").closest(".dashboard-form-globalfilters").css("display", d);
        $(".dashboard-form-globalfieldset").css("display", d);
        $(".dashboard-header-description").css("display", d);
    }

    function packToRow(pack) {
        if (!pack) {
            console.log(logPrefix, "packToRow", "(no pack)");
            return null;
        }
        if (Array.isArray(pack)) {
            var ar = pack.length ? pack[0] : null;
            console.log(logPrefix, "packToRow", "array pack, first row", ar);
            return ar;
        }
        var rows = pack.rows;
        var fields = pack.fields;
        if (!rows || !rows.length) {
            console.log(logPrefix, "packToRow", "(no rows)", { fields: fields });
            return null;
        }
        var names = fieldNames(fields);
        var row = rows[0];
        if (row && typeof row === "object" && !Array.isArray(row)) {
            console.log(logPrefix, "packToRow", "object row", row);
            return row;
        }
        if (!names.length || !Array.isArray(row)) {
            console.log(logPrefix, "packToRow", "(cannot map)", { names: names, row: row });
            return null;
        }
        var obj = {};
        names.forEach(function(name, i) {
            if (name) {
                obj[name] = row[i];
            }
        });
        console.log(logPrefix, "packToRow", "mapped row", obj);
        return obj;
    }

    function runRegionSearch(cb) {
        console.log(logPrefix, "runRegionSearch", "start", "| workshopregion action=\"status\"");
        var resolved = false;
        function finalize(row) {
            console.log(logPrefix, "runRegionSearch.finalize", row);
            if (resolved) {
                return;
            }
            resolved = true;
            if (cb) {
                cb(row);
            }
        }

        var results = regionSearch.data("results", { count: 50, offset: 0 });

        function readRow() {
            if (!results.hasData()) {
                console.log(logPrefix, "runRegionSearch.readRow", "(no results yet)");
                return null;
            }
            var row = packToRow(results.data());
            console.log(logPrefix, "runRegionSearch.readRow", row);
            return row;
        }

        results.once("data", function() {
            console.log(logPrefix, "runRegionSearch", 'results "data"');
            finalize(readRow());
        });

        regionSearch.once("search:error", function(err) {
            console.log(logPrefix, "runRegionSearch", "search:error", err);
            finalize(null);
        });

        regionSearch.once("search:failed", function(state) {
            console.log(logPrefix, "runRegionSearch", "search:failed", state);
            finalize(null);
        });

        regionSearch.startSearch();
    }

    function applyVisibilityFromReady() {
        var r =
            defaultTokenModelun.get("status_region_ready") || submittedTokenModelun.get("status_region_ready");
        // Undefined before status completes must stay hidden (unknown), not behave like region_ready=false.
        var rs =
            r === undefined || r === null
                ? ""
                : String(r).toLowerCase();
        console.log(logPrefix, "applyVisibilityFromReady", "status_region_ready raw:", r, "normalized:", rs);
        if (rs === "true") {
            setControlHidden(true);
        } else if (rs === "false") {
            setControlHidden(false);
        } else {
            setControlHidden(true);
        }
    }
});
