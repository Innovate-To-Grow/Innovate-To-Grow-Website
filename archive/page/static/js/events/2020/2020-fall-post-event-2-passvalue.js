function passvalue(slot) {
    window.document.location = 'https://innovatetogrow.ucmerced.edu/' + '?value=' + encodeURIComponent(document.getElementById(slot).textContent) + '#projects';
}
