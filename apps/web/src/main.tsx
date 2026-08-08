import '@ant-design/v5-patch-for-react-19'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import './index.css'
import App from './App.tsx'
import { ActorProvider } from './ActorContext.tsx'

const theme = {
  token: {
    colorPrimary: '#7c3aed',
    colorInfo: '#7c3aed',
    borderRadius: 10,
    fontFamily:
      '"IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontSize: 14,
    colorBgLayout: '#f7f7fb',
  },
  components: {
    Layout: {
      siderBg: '#151321',
      headerBg: '#ffffff',
      bodyBg: '#f7f7fb',
    },
    Menu: {
      darkItemBg: '#151321',
      darkItemSelectedBg: 'rgba(139, 92, 246, 0.22)',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.06)',
      darkItemColor: 'rgba(255, 255, 255, 0.75)',
      darkItemSelectedColor: '#ffffff',
      itemBorderRadius: 8,
    },
    Card: {
      borderRadiusLG: 14,
    },
  },
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider theme={theme}>
      <AntApp>
        <ActorProvider>
          <App />
        </ActorProvider>
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
)
