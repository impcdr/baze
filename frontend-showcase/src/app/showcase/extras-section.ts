import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { NgScrollbar } from 'ngx-scrollbar';
import { provideNativeDateAdapter } from '@spartan-ng/brain/date-time';
import { HlmAccordionImports } from '@spartan-ng/helm/accordion';
import { HlmAlertDialogImports } from '@spartan-ng/helm/alert-dialog';
import { HlmAspectRatioImports } from '@spartan-ng/helm/aspect-ratio';
import { HlmAutocompleteImports } from '@spartan-ng/helm/autocomplete';
import { HlmBreadcrumbImports } from '@spartan-ng/helm/breadcrumb';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmButtonGroupImports } from '@spartan-ng/helm/button-group';
import { HlmCalendarImports } from '@spartan-ng/helm/calendar';
import { HlmCarouselImports } from '@spartan-ng/helm/carousel';
import { HlmCheckboxImports } from '@spartan-ng/helm/checkbox';
import { HlmCodeBlockImports } from '@spartan-ng/helm/code-block';
import { HlmCollapsibleImports } from '@spartan-ng/helm/collapsible';
import { HlmComboboxImports } from '@spartan-ng/helm/combobox';
import { HlmCommandImports } from '@spartan-ng/helm/command';
import { HlmContextMenuImports } from '@spartan-ng/helm/context-menu';
import { HlmDatePickerImports } from '@spartan-ng/helm/date-picker';
import { HlmDrawerImports } from '@spartan-ng/helm/drawer';
import { HlmDropdownMenuImports } from '@spartan-ng/helm/dropdown-menu';
import { HlmHoverCardImports } from '@spartan-ng/helm/hover-card';
import { HlmInputOtpImports } from '@spartan-ng/helm/input-otp';
import { HlmLabelImports } from '@spartan-ng/helm/label';
import { HlmMarkerImports } from '@spartan-ng/helm/marker';
import { HlmMenubarImports } from '@spartan-ng/helm/menubar';
import { HlmNavigationMenuImports } from '@spartan-ng/helm/navigation-menu';
import { HlmPaginationImports } from '@spartan-ng/helm/pagination';
import { HlmPopoverImports } from '@spartan-ng/helm/popover';
import { HlmQuestionnaireImports } from '@spartan-ng/helm/questionnaire';
import { HlmRadioGroupImports } from '@spartan-ng/helm/radio-group';
import { HlmResizableImports } from '@spartan-ng/helm/resizable';
import { HlmScrollAreaImports } from '@spartan-ng/helm/scroll-area';
import { HlmSelectImports } from '@spartan-ng/helm/select';
import { HlmSliderImports } from '@spartan-ng/helm/slider';
import { HlmSwitchImports } from '@spartan-ng/helm/switch';
import { HlmToggleImports } from '@spartan-ng/helm/toggle';
import { HlmTraceImports } from '@spartan-ng/helm/trace';
import { HlmTypographyImports } from '@spartan-ng/helm/typography';

@Component({
  selector: 'bz-spartan-extras',
  imports: [
    NgScrollbar,
    ...HlmAccordionImports,
    ...HlmAlertDialogImports,
    ...HlmAspectRatioImports,
    ...HlmAutocompleteImports,
    ...HlmBreadcrumbImports,
    ...HlmButtonImports,
    ...HlmButtonGroupImports,
    ...HlmCalendarImports,
    ...HlmCarouselImports,
    ...HlmCheckboxImports,
    ...HlmCodeBlockImports,
    ...HlmCollapsibleImports,
    ...HlmComboboxImports,
    ...HlmCommandImports,
    ...HlmContextMenuImports,
    ...HlmDatePickerImports,
    ...HlmDrawerImports,
    ...HlmDropdownMenuImports,
    ...HlmHoverCardImports,
    ...HlmInputOtpImports,
    ...HlmLabelImports,
    ...HlmMarkerImports,
    ...HlmMenubarImports,
    ...HlmNavigationMenuImports,
    ...HlmPaginationImports,
    ...HlmPopoverImports,
    ...HlmQuestionnaireImports,
    ...HlmRadioGroupImports,
    ...HlmResizableImports,
    ...HlmScrollAreaImports,
    ...HlmSelectImports,
    ...HlmSliderImports,
    ...HlmSwitchImports,
    ...HlmToggleImports,
    ...HlmTraceImports,
    ...HlmTypographyImports,
  ],
  providers: [provideNativeDateAdapter()],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './extras-section.html',
  host: { class: 'block min-w-0' },
})
export class SpartanExtras {
  protected readonly page = signal(1);
  protected readonly pageSize = signal(10);
}
