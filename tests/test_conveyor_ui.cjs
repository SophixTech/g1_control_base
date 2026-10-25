const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('web_client/static/app.js', 'utf8');
const code = source.slice(source.indexOf('function canToggleControl()'), source.indexOf('function setThreadControlUI()'));
const context = {App:{isRunning:true,isObserveRunning:true,isInferenceRunning:false,isControlRunning:false,conveyorEnabled:false}};
vm.createContext(context); vm.runInContext(code,context);
assert.equal(context.canToggleControl(),false); // Legacy requires Infer Start.
context.App.conveyorEnabled=true;
assert.equal(context.canToggleControl(),true); // Gate can arm from Observe only.
context.App.isControlRunning=true;
assert.equal(context.canToggleControl(),true); // Waiting gate can always Stop, even with inference off.
context.App.isObserveRunning=false;
assert.equal(context.canToggleControl(),true); // Stop remains available after observation fails.
context.App.isControlRunning=false;
assert.equal(context.canToggleControl(),false);
console.log('Conveyor Control button tests passed');
