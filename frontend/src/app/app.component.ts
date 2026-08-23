import { Component } from '@angular/core';
import { HeaderComponent } from './components/header/header.component';
import { MetricsBarComponent } from './components/metrics-bar/metrics-bar.component';
import { LogFilterComponent } from './components/log-filter/log-filter.component';
import { LogTableComponent } from './components/log-table/log-table.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    HeaderComponent,
    MetricsBarComponent,
    LogFilterComponent,
    LogTableComponent
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent {
  title = 'Nightshift AI SRE - Live Log Viewer';
}
