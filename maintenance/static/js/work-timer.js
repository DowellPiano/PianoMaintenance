(function () {
  "use strict";

  function twoDigits(value) {
    return String(value).padStart(2, "0");
  }

  function formatDuration(milliseconds) {
    var totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    var hours = Math.floor(totalSeconds / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;

    return [hours, minutes, seconds].map(twoDigits).join(":");
  }

  function formatTime(date) {
    return date.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function elapsedHours(startAt, endAt) {
    return ((endAt.getTime() - startAt.getTime()) / 3600000).toFixed(2);
  }

  function setDisabled(button, disabled) {
    if (!button) {
      return;
    }
    button.disabled = disabled;
  }

  function setupTimer(timer) {
    var input = document.getElementById(timer.dataset.hoursInputId || "id_hours_worked");
    var storageKey = timer.dataset.workTimerStorageKey;
    var elapsed = timer.querySelector("[data-work-timer-elapsed]");
    var startTime = timer.querySelector("[data-work-timer-start-time]");
    var endTime = timer.querySelector("[data-work-timer-end-time]");
    var startButton = timer.querySelector("[data-work-timer-start]");
    var endButton = timer.querySelector("[data-work-timer-end]");
    var resetButton = timer.querySelector("[data-work-timer-reset]");
    var startAt = null;
    var endAt = null;
    var intervalId = null;
    var lastTimerValue = null;
    var syncingInput = false;

    if (!input || !elapsed || !startButton || !endButton || !resetButton) {
      return;
    }

    function stopTicking() {
      if (intervalId) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    }

    function render() {
      var displayEnd = endAt || new Date();
      elapsed.textContent = startAt ? formatDuration(displayEnd.getTime() - startAt.getTime()) : "00:00:00";
      startTime.textContent = startAt ? formatTime(startAt) : "--";
      endTime.textContent = endAt ? formatTime(endAt) : "--";

      setDisabled(startButton, Boolean(startAt && !endAt));
      setDisabled(endButton, !startAt || Boolean(endAt));
      setDisabled(resetButton, !startAt && !endAt);
    }

    function dispatchInputEvents() {
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function removeStoredState() {
      if (!storageKey) {
        return;
      }

      try {
        window.localStorage.removeItem(storageKey);
      } catch (error) {
        // The timer still works for this page when browser storage is unavailable.
      }
    }

    function storeState() {
      if (!storageKey || !startAt) {
        return;
      }

      try {
        window.localStorage.setItem(storageKey, JSON.stringify({
          startAt: startAt.toISOString(),
          endAt: endAt ? endAt.toISOString() : null,
        }));
      } catch (error) {
        // The timer still works for this page when browser storage is unavailable.
      }
    }

    function restoreState() {
      if (!storageKey) {
        return;
      }

      try {
        var storedState = JSON.parse(window.localStorage.getItem(storageKey));
        if (!storedState || !storedState.startAt) {
          return;
        }

        var storedStartAt = new Date(storedState.startAt);
        var storedEndAt = storedState.endAt ? new Date(storedState.endAt) : null;
        if (
          Number.isNaN(storedStartAt.getTime()) ||
          (storedEndAt && (
            Number.isNaN(storedEndAt.getTime()) ||
            storedEndAt.getTime() < storedStartAt.getTime()
          ))
        ) {
          removeStoredState();
          return;
        }

        startAt = storedStartAt;
        endAt = storedEndAt;

        if (endAt) {
          var restoredTimerValue = elapsedHours(startAt, endAt);
          if (!input.value) {
            syncingInput = true;
            input.value = restoredTimerValue;
            dispatchInputEvents();
            syncingInput = false;
          }
          if (input.value === restoredTimerValue) {
            lastTimerValue = restoredTimerValue;
          }
        }
      } catch (error) {
        removeStoredState();
      }
    }

    function clearTimerValueIfCurrent() {
      if (lastTimerValue !== null && input.value === lastTimerValue) {
        syncingInput = true;
        input.value = "";
        dispatchInputEvents();
        syncingInput = false;
      }
      lastTimerValue = null;
    }

    input.addEventListener("input", function () {
      if (!syncingInput && input.value !== lastTimerValue) {
        lastTimerValue = null;
      }
    });

    startButton.addEventListener("click", function () {
      stopTicking();
      clearTimerValueIfCurrent();
      startAt = new Date();
      endAt = null;
      storeState();
      render();
      intervalId = window.setInterval(render, 1000);
    });

    endButton.addEventListener("click", function () {
      if (!startAt) {
        return;
      }

      endAt = new Date();
      stopTicking();
      storeState();
      lastTimerValue = elapsedHours(startAt, endAt);
      syncingInput = true;
      input.value = lastTimerValue;
      dispatchInputEvents();
      syncingInput = false;
      render();
    });

    resetButton.addEventListener("click", function () {
      stopTicking();
      clearTimerValueIfCurrent();
      startAt = null;
      endAt = null;
      removeStoredState();
      render();
    });

    var form = timer.closest("form");
    if (form) {
      form.addEventListener("submit", removeStoredState);
    }

    restoreState();
    render();
    if (startAt && !endAt) {
      intervalId = window.setInterval(render, 1000);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-work-timer]").forEach(setupTimer);
  });
})();
