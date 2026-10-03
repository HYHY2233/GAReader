'use strict';
(() => {
 const user=document.body.dataset.readerUser;let preferences={};
 try{preferences=JSON.parse(localStorage.getItem(`gareader:preferences:v2:${user}`)||'{}');}catch{}
 const theme=preferences.theme||'auto',system=matchMedia('(prefers-color-scheme: dark)');
 const apply=()=>{if(document.getElementById('reader'))return;document.documentElement.classList.toggle('dark',theme==='dark'||theme==='auto'&&system.matches);document.documentElement.classList.toggle('sepia',theme==='sepia');};
 apply();system.addEventListener('change',apply);
})();
window.notify = function(text, error=false) { const n=document.getElementById('toast'); n.textContent=text; n.classList.toggle('error',error); n.classList.add('visible'); clearTimeout(window.toastTimer); window.toastTimer=setTimeout(()=>n.classList.remove('visible'),5000); };
