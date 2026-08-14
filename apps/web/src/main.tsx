import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import './index.css'
import App from './App.tsx'
import { ActorProvider } from './ActorContext.tsx'

const theme = {
  token: {
    colorPrimary: '#5b4db1',
    colorInfo: '#5b4db1',
    borderRadius: 8,
    fontFamily:
      '"IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontSize: 13,
    // A review tool is read at desk distance for long sessions, so the type
    // scale is set here rather than patched in CSS: antd derives heading sizes,
    // control heights and line-heights from these tokens, so overriding only
    // font-size downstream gives you small text inside unchanged 40px controls.
    fontSizeSM: 12,
    fontSizeLG: 15,
    fontSizeHeading3: 19,
    fontSizeHeading4: 15,
    fontSizeHeading5: 14,
    lineHeight: 1.5,
    controlHeight: 30,
    controlHeightSM: 24,
    controlHeightLG: 36,
    colorBgLayout: '#f4f5f7',
    colorBorderSecondary: '#e3e6eb',
  },
  components: {
    Layout: {
      siderBg: '#171826',
      headerBg: '#ffffff',
      bodyBg: '#f4f5f7',
    },
    Menu: {
      darkItemBg: '#171826',
      darkItemSelectedBg: 'rgba(99, 102, 241, 0.22)',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.06)',
      darkItemColor: 'rgba(255, 255, 255, 0.75)',
      darkItemSelectedColor: '#ffffff',
      itemBorderRadius: 6,
    },
    Card: {
      borderRadiusLG: 10,
      headerBg: '#fbfbfc',
      headerFontSize: 13,
      headerFontSizeSM: 12,
      headerHeight: 42,
      headerHeightSM: 36,
      bodyPadding: 14,
      bodyPaddingSM: 12,
      headerPadding: 14,
      headerPaddingSM: 12,
      actionsBg: '#fbfbfc',
      extraColor: '#64748b',
    },
    Button: {
      fontWeight: 500,
      iconGap: 6,
      defaultShadow: 'none',
      primaryShadow: 'none',
      dangerShadow: 'none',
      defaultBorderColor: '#d5d9e0',
      defaultHoverBorderColor: '#8f86c4',
      defaultHoverColor: '#51458f',
    },
    Modal: {
      headerBg: '#ffffff',
      titleFontSize: 15,
      titleLineHeight: 1.35,
      titleColor: '#171b26',
      contentBg: '#ffffff',
      footerBg: '#fafbfc',
    },
    Drawer: {
      footerPaddingBlock: 10,
      footerPaddingInline: 16,
    },
    Popover: {
      titleMinWidth: 180,
    },
    Tooltip: {
      maxWidth: 360,
    },
    Alert: {
      defaultPadding: '8px 12px',
      withDescriptionPadding: '10px 12px',
      withDescriptionIconSize: 16,
    },
    Collapse: {
      headerPadding: '10px 12px',
      headerPaddingSM: '8px 10px',
      headerPaddingLG: '12px 14px',
      contentPadding: '12px',
      contentPaddingSM: '10px',
      contentPaddingLG: '14px',
      headerBg: '#f7f8fa',
      contentBg: '#ffffff',
      collapsePanelBorderRadius: 8,
    },
    Descriptions: {
      labelBg: '#f7f8fa',
      labelColor: '#616b78',
      titleColor: '#171b26',
      titleMarginBottom: 10,
      itemPaddingBottom: 8,
      itemPaddingEnd: 12,
      contentColor: '#273142',
      extraColor: '#64748b',
    },
    Select: {
      optionSelectedColor: '#342c69',
      optionSelectedFontWeight: 600,
      optionSelectedBg: '#efedf8',
      optionActiveBg: '#f6f5fa',
      optionPadding: '5px 10px',
      optionFontSize: 12,
      optionLineHeight: 1.45,
      optionHeight: 30,
      hoverBorderColor: '#8f86c4',
      activeBorderColor: '#5b4db1',
      activeOutlineColor: 'rgba(91, 77, 177, 0.12)',
    },
    Statistic: {
      contentFontSize: 20,
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
