import fs from 'node:fs';

const required = [
  'tritobol_app/static/index.html',
  'tritobol_app/static/css/tritobol.css',
  'tritobol_app/static/js/app.js',
  'tritobol_app/static/js/history.js',
  'tritobol_app/static/favicon.svg',
];
let failed = false;
for (const file of required) {
  if (!fs.existsSync(file)) {
    console.error(`Missing ${file}`);
    failed = true;
  }
}
const html = fs.readFileSync('tritobol_app/static/index.html', 'utf8');
for (const id of ['view-dashboard', 'view-optimize', 'view-results', 'view-analytics', 'view-history', 'view-privacy', 'view-settings', 'view-home', 'view-features', 'view-about', 'view-contact', 'view-terms', 'view-signin', 'view-signup', 'view-forgot', 'view-reset']) {
  if (!html.includes(`id="${id}"`)) {
    console.error(`index.html is missing #${id}`);
    failed = true;
  }
}
if (failed) process.exit(1);
console.log('Tritobol has no frontend bundler. Flask serves tritobol_app/static and injects the session token when it renders index.html.');
