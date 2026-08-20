import {StatusApp} from './app'

const root = document.querySelector<HTMLElement>('#status-root')
const announcer = document.querySelector<HTMLElement>('#status-announcer')

if (root && announcer) {
  new StatusApp(root, announcer).start()
}
