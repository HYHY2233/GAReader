'use strict';
window.notify = function(text, error=false) { const n=document.getElementById('toast'); n.textContent=text; n.classList.toggle('error',error); n.classList.add('visible'); clearTimeout(window.toastTimer); window.toastTimer=setTimeout(()=>n.classList.remove('visible'),5000); };
