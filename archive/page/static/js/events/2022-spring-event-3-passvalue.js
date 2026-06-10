function passvalue(slot) {
    window.document.location = window.location.pathname + '?value=' + encodeURIComponent(document.getElementById(slot).textContent) + '#projects';
}
