import { Tooltip, TooltipContent, TooltipTrigger } from './overlay';

export function SampleMark() {
  return (
    <Tooltip>
      <TooltipTrigger>
        <button type="button" className="sample-mark">Sample</button>
      </TooltipTrigger>
      <TooltipContent>Hand-written layout. Not a measurement.</TooltipContent>
    </Tooltip>
  );
}
