import { links, projects, posts } from './config.js'

const linksEl = document.querySelector('.links')
links.forEach(link => {
  linksEl.innerHTML += `
    <li>
      <a href="${link.url}" class="link">
        <img class="link-icon" src="../assets/brands/${link.icon}" alt="${link.text}" />
        <span class="link-text">${link.text}</span>
      </a>
    </li>
  `
})
