import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'molstar/lib/mol-plugin-ui/skin/light.scss'

import App from './App.vue'
import './style.css'

const app = createApp(App)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
