(function () {
  "use strict";

  var year = document.getElementById("yr");
  if (year) year.textContent = String(new Date().getFullYear());

  var nav = document.getElementById("nav");
  var burger = document.getElementById("hbtn");
  var navlinks = document.getElementById("navlinks");

  function setNav(open) {
    if (!nav || !burger) return;
    nav.classList.toggle("open", open);
    document.body.classList.toggle("nav-open", open);
    burger.setAttribute("aria-expanded", open ? "true" : "false");
    burger.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }

  if (nav && burger) {
    burger.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      setNav(!nav.classList.contains("open"));
    });
    if (navlinks) {
      navlinks.addEventListener("click", function (event) {
        if (event.target.closest("a")) setNav(false);
      });
    }
    document.addEventListener("click", function (event) {
      if (nav.classList.contains("open") && !nav.contains(event.target)) {
        setNav(false);
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setNav(false);
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth >= 900) setNav(false);
    });
  }

  document.querySelectorAll(".nav-group-trigger").forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      event.stopPropagation();
      var group = trigger.closest(".nav-group");
      var next = !group.classList.contains("open");
      document.querySelectorAll(".nav-group.open").forEach(function (item) {
        if (item !== group) {
          item.classList.remove("open");
          var button = item.querySelector(".nav-group-trigger");
          if (button) button.setAttribute("aria-expanded", "false");
        }
      });
      group.classList.toggle("open", next);
      trigger.setAttribute("aria-expanded", next ? "true" : "false");
    });
  });

  document.addEventListener("click", function (event) {
    if (!event.target.closest(".nav-group")) {
      document.querySelectorAll(".nav-group.open").forEach(function (group) {
        group.classList.remove("open");
        var trigger = group.querySelector(".nav-group-trigger");
        if (trigger) trigger.setAttribute("aria-expanded", "false");
      });
    }
  });

  document.querySelectorAll("form[data-waitlist]").forEach(function (form) {
    var message = form.parentElement.querySelector(".msg");
    var button = form.querySelector('button[type="submit"]');
    var input = form.querySelector('input[type="email"]');

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!input || !button) return;
      var email = input.value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        if (message) {
          message.className = "msg err";
          message.textContent = "Enter a valid email address.";
        }
        return;
      }

      var original = button.textContent;
      button.disabled = true;
      button.textContent = "Joining…";
      if (message) {
        message.className = "msg";
        message.textContent = "";
      }

      fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email,
          segment: form.getAttribute("data-waitlist") || "general",
          ref: location.pathname + location.search,
        }),
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok) throw new Error(data.error || "request_failed");
            return data;
          });
        })
        .then(function () {
          form.hidden = true;
          if (message) {
            message.className = "msg ok";
            message.textContent = "You're on the list. We'll send relevant delivery updates.";
          }
        })
        .catch(function () {
          button.disabled = false;
          button.textContent = original;
          if (message) {
            message.className = "msg err";
            message.textContent = "Could not join right now. Email info@abakos.ai instead.";
          }
        });
    });
  });

  var canvas = document.getElementById("grid");
  if (canvas && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var context = canvas.getContext("2d");
    var width = 0;
    var height = 0;
    var points = [];
    var gap = 34;

    // Read the brand colors from CSS instead of hardcoding a second copy --
    // this is the exact bug that made the hero animation render a visibly
    // different blue than the buttons/logo. One token, one color, always.
    var rootStyle = getComputedStyle(document.documentElement);
    var brandLight = (rootStyle.getPropertyValue("--abk-brand-light-rgb") || "91, 141, 255").trim();
    var mutedRgb = "150, 156, 175";

    function resizeGrid() {
      var box = canvas.parentElement.getBoundingClientRect();
      var ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = box.width;
      height = box.height;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      canvas.style.width = width + "px";
      canvas.style.height = height + "px";
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      points = [];
      for (var y = gap / 2; y < height; y += gap) {
        for (var x = gap / 2; x < width; x += gap) {
          points.push([x, y]);
        }
      }
    }

    function drawGrid(time) {
      context.clearRect(0, 0, width, height);
      var sweep = (time * 0.055) % (width + 320) - 160;
      points.forEach(function (point) {
        var distance = Math.abs(point[0] - sweep);
        var intensity = Math.max(0, 1 - distance / 210);
        context.globalAlpha = 0.16 + intensity * 0.62;
        context.fillStyle = intensity > 0.16 ? "rgb(" + brandLight + ")" : "rgb(" + mutedRgb + ")";
        context.beginPath();
        context.arc(point[0], point[1], 1.3 + intensity * 2, 0, Math.PI * 2);
        context.fill();
      });
      requestAnimationFrame(drawGrid);
    }

    resizeGrid();
    window.addEventListener("resize", resizeGrid);
    requestAnimationFrame(drawGrid);
  }
})();
