import { useTranslation } from 'react-i18next'

import { Icon } from '@/components/icons/Icon'
import { button } from '@/components/m3/styles'

export function LanguageToggle() {
  const { t, i18n } = useTranslation()
  const next = i18n.language === 'zh' ? 'en' : 'zh'
  return (
    <button
      type="button"
      onClick={() => void i18n.changeLanguage(next)}
      aria-label={t('common.language')}
      className={button('text', 'sm', 'text-on-surface-variant')}
    >
      <Icon name="translate" />
      <span lang={next === 'zh' ? 'zh-Hans' : 'en'}>{t('common.switchTo')}</span>
    </button>
  )
}
