#!/usr/bin/env node

/*
  Released under MIT license. See the accompanying LICENSE.txt file for
  full terms and conditions

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.

*/

function usage ( ) {
    console.log('usage: ', process.argv[1], '<target> <duration> [starttime]');
    console.log('example: ', process.argv[1], '110 60');
    console.log('example: ', process.argv[1], '120 30 2017-10-18:00:15:00.000Z');
}

if (!module.parent) {
    var target = process.argv[2];
    var duration = process.argv[3];
    var start = process.argv[4];

    if ([null, '--help', '-h', 'help'].indexOf(target) > 0) {
        usage( );
        process.exit(0)
    }
    if (!target || !duration) {
        usage( )
        process.exit(1);
    }

    var temptarget = {};
    temptarget.targetBottom = parseInt(target);
    temptarget.targetTop = parseInt(target);
    temptarget.duration = parseInt(duration);
    if (start) {
        temptarget.created_at = new Date(start);
    } else {
        temptarget.created_at = new Date();
    }


    console.log(JSON.stringify(temptarget));
}

