(function () {
    const html = document.documentElement;
    const savedTheme = localStorage.getItem("theme") || html.dataset.bsTheme || "light";

    html.dataset.bsTheme = savedTheme;

    function updateIcon(theme) {
        const icon = document.getElementById("theme-icon");
        if (icon) {
            icon.src = theme === "dark"
                ? "/static/icons/icons8-light-mode-78.png"
                : "/static/icons/icons8-dark-mode-100.png";
        }
    }

    // 👉 применяем при загрузке
    updateIcon(savedTheme);

    window.toggleTheme = function () {
        const isDark = html.dataset.bsTheme === "dark";
        const newTheme = isDark ? "light" : "dark";

        html.dataset.bsTheme = newTheme;
        localStorage.setItem("theme", newTheme);

        // 👉 применяем при переключении
        updateIcon(newTheme);
    };
    document.addEventListener("DOMContentLoaded", function () {
        const btn = document.getElementById("theme-toggle");
        if (btn) {
            btn.addEventListener("click", window.toggleTheme);
        }
    });
    window.addEventListener("scroll", function () {
        const navbar = document.querySelector(".app-navbar");

        if (window.scrollY > 10) {
            navbar.style.boxShadow = "0 4px 20px rgba(0,0,0,0.1)";
        } else {
            navbar.style.boxShadow = "none";
        }
    });





})();
