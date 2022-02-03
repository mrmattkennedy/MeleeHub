function checkboxClicked(src) {
    var checked = src.parentNode.getElementsByTagName('input')[0].checked
    src.parentNode.getElementsByTagName('input')[0].checked = !checked
}